"""
This code creates some test agent and registers until the user stops the process.
For this we wait for SIGINT.
"""
import logging
from sc_client.models import ScAddr, ScLinkContentType, ScTemplate
from sc_client.constants import sc_types
from sc_client.client import template_search

from sc_kpm import ScAgentClassic, ScModule, ScResult, ScServer
from sc_kpm.sc_sets import ScSet
from sc_kpm.utils import (
    create_link,
    get_link_content_data,
    check_edge, create_edge,
    delete_edges,
    get_element_by_role_relation,
    get_element_by_norole_relation,
    get_system_idtf,
    get_edge
)
from sc_kpm.utils.action_utils import (
    create_action_answer,
    finish_action_with_status,
    get_action_arguments,
    get_element_by_role_relation
)
from sc_kpm import ScKeynodes

import requests


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s", datefmt="[%d-%b-%y %H:%M:%S]"
)


class StockPriceAgent(ScAgentClassic):
    def __init__(self):
        print('StockAgent initialized')
        super().__init__("action_show_stock_price")

    def on_event(self, event_element: ScAddr, event_edge: ScAddr, action_element: ScAddr) -> ScResult:
        result = self.run(action_element)
        is_successful = result == ScResult.OK
        finish_action_with_status(action_element, is_successful)
        self.logger.info("StockPriceAgent finished %s",
                         "successfully" if is_successful else "unsuccessfully")
        return result

    def run(self, action_node: ScAddr) -> ScResult:
        self.logger.info("StockPriceAgent started")

        try:
            message_addr = get_action_arguments(action_node, 1)[0]
            message_type = ScKeynodes.resolve(
                "concept_message_about_stock_price", sc_types.NODE_CONST_CLASS)

            if not check_edge(sc_types.EDGE_ACCESS_VAR_POS_PERM, message_type, message_addr):
                self.logger.info(
                    f"StockPriceAgent: the message isn’t about stock price")
                return ScResult.OK

            idtf = ScKeynodes.resolve("nrel_idtf", sc_types.NODE_CONST_NOROLE)
            answer_phrase = ScKeynodes.resolve(
                "show_stock_price_answer_phrase", sc_types.NODE_CONST_CLASS)
            rrel_entity = ScKeynodes.resolve("rrel_entity", sc_types.NODE_ROLE)
            nrel_price = ScKeynodes.resolve("nrel_price", sc_types.NODE_NOROLE)

            company_addr = self.get_entity_addr(message_addr, rrel_entity)

            self.clear_previous_answer(company_addr, nrel_price, answer_phrase)            

            # If there is no such company
            if not company_addr.is_valid():
                self.set_unknown_company_link(action_node, answer_phrase)
                return ScResult.OK
            city_idtf_link = self.get_ru_idtf(company_addr)
            answer_company_idtf_link = get_element_by_norole_relation(
                src=company_addr, nrel_node=idtf)
            if not city_idtf_link.is_valid():
                self.set_unknown_company_link(action_node, answer_phrase)
                return ScResult.OK
        except:
            self.logger.info(f"StockPriceAgent: finished with an error")
            return ScResult.ERROR

        entity_idtf = get_link_content_data(city_idtf_link)
        try:
            stock_price = self.get_stock_price(company_addr)
        except requests.exceptions.ConnectionError:
            self.logger.info(f"StockPriceAgent: finished with connection error")
            return ScResult.ERROR
        except KeyError as e:
            self.logger.error(f"StockPriceAgent: {e}")
            return ScResult.ERROR
        link = create_link(str(stock_price), ScLinkContentType.STRING, link_type=sc_types.LINK_CONST)
        stock_price_edge = create_edge(sc_types.EDGE_D_COMMON_CONST, company_addr, link)
        create_edge(sc_types.EDGE_ACCESS_CONST_POS_PERM, nrel_price, stock_price_edge)
        create_action_answer(action_node, link)

        return ScResult.OK

    def get_stock_price(self, company_addr: ScAddr) -> float:
        ticker: str | None = None        
        company_tickets = ScKeynodes.resolve("nrel_company_cipher", sc_types.NODE_CONST_NOROLE)
        lang_ru = ScKeynodes.resolve("lang_ru", sc_types.NODE_CONST_CLASS)        
        template = ScTemplate()
        template.triple_with_relation(
            company_addr,
            sc_types.EDGE_D_COMMON_VAR,
            sc_types.LINK,
            sc_types.EDGE_ACCESS_VAR_POS_PERM,
            company_tickets
        )
        search_results = template_search(template)
        for result in search_results:
            idtf = result[2]
            lang_edge = get_edge(
                lang_ru, idtf, sc_types.EDGE_ACCESS_VAR_POS_PERM)
            if lang_edge:
                ticker = idtf
                break
        if ticker is None:
            raise KeyError("No ticker for that company in knowledge base!")

        # Get stock price by ticker
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {
            "interval": "1h",
            "range": "1d"
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # Extract current stock price
        current_price = data['chart']['result'][0]['meta']['regularMarketPrice']
        self.logger.info(f"StockPriceAgent: current stock price: {current_price} USD")
        return current_price

    def set_unknown_company_link(self, action_node: ScAddr, answer_phrase: ScAddr) -> None:
        unknown_city_link = ScKeynodes.resolve(
            "unknown_company_for_stock_price_agent_message_text", None)
        if not unknown_city_link.is_valid():
            raise
        create_edge(
            sc_types.EDGE_ACCESS_CONST_POS_PERM, answer_phrase, unknown_city_link)
        create_action_answer(action_node, unknown_city_link)

    def get_ru_idtf(self, entity_addr: ScAddr) -> ScAddr:
        main_idtf = ScKeynodes.resolve(
            "nrel_main_idtf", sc_types.NODE_CONST_NOROLE)
        lang_ru = ScKeynodes.resolve("lang_ru", sc_types.NODE_CONST_CLASS)

        template = ScTemplate()
        template.triple_with_relation(
            entity_addr,
            sc_types.EDGE_D_COMMON_VAR,
            sc_types.LINK,
            sc_types.EDGE_ACCESS_VAR_POS_PERM,
            main_idtf,
        )
        search_results = template_search(template)
        for result in search_results:
            idtf = result[2]
            lang_edge = get_edge(
                lang_ru, idtf, sc_types.EDGE_ACCESS_VAR_POS_PERM)
            if lang_edge:
                return idtf
        return get_element_by_norole_relation(
            src=entity_addr, nrel_node=main_idtf)

    def get_entity_addr(self, message_addr: ScAddr, rrel_entity: ScAddr):
        rrel_entity = ScKeynodes.resolve("rrel_entity", sc_types.NODE_ROLE)        
        template = ScTemplate()
        # entity node or link
        template.triple_with_relation(
            message_addr,
            sc_types.EDGE_ACCESS_VAR_POS_PERM,
            sc_types.VAR,
            sc_types.EDGE_ACCESS_VAR_POS_PERM,
            rrel_entity,
        )
        search_results = template_search(template)
        if len(search_results) == 0:
            return ScAddr(0)
        entity = search_results[0][2]
        if len(search_results) == 1:
            return entity        

    def clear_previous_answer(self, entity, nrel_price, answer_phrase):
        message_answer_set = ScSet(set_node=answer_phrase)
        message_answer_set.clear()
        if not entity.is_valid():
            return

        template = ScTemplate()
        template.triple_with_relation(
            entity,
            sc_types.EDGE_D_COMMON_VAR,
            sc_types.LINK,
            sc_types.EDGE_ACCESS_VAR_POS_PERM,
            nrel_price
        )
        search_results = template_search(template)
        for result in search_results:
            delete_edges(result[0], result[2], sc_types.EDGE_D_COMMON_VAR)
