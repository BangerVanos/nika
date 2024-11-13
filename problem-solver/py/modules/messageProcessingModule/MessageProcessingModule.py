from sc_kpm import ScModule
from .WeatherAgent import WeatherAgent
from .StockPriceAgent import StockPriceAgent


class MessageProcessingModule(ScModule):
    def __init__(self):
        super().__init__(WeatherAgent(), StockPriceAgent())
