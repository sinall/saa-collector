import re
from enum import Enum, auto

class StockExchange(Enum):
    UNKNOWN = auto()  # 未知交易所
    SSE = auto()     # 上海证券交易所
    SZSE = auto()    # 深圳证券交易所
    BSE = auto()     # 北京证券交易所
    HKEX = auto()    # 香港交易所

    def __str__(self):
        # 自定义字符串表示
        if self == StockExchange.SSE:
            return "SH"
        elif self == StockExchange.SZSE:
            return "SZ"
        elif self == StockExchange.BSE:
            return "BJ"
        elif self == StockExchange.HKEX:
            return "HK"
        return self.name  # 其他成员保持默认名称

class StockBoard(Enum):
    MAIN_BOARD = auto()                   # 主板
    SMALL_AND_MEDIUM_ENTERPRISES = auto() # 中小板
    CHINEXT = auto()                      # 创业板
    STAR = auto()                         # 科创板
    ST = auto()                           # ST/*ST/SST/S*ST

    def __str__(self):
        return self.name

class StockUtils:
    @staticmethod
    def format(code, fmt):
        market = StockUtils.to_exchange(code)
        return fmt.format(market=market, code=code)

    @staticmethod
    def to_exchange(symbol):
        """根据证券代码判断所属交易所"""
        SH_SECURITY_PREFIXES = {
            "009", "010", "019",  # 国债
            "018",  # 国开债
            "110", "111", "113", "118", "126",  # 可转债
            "132",  # 可交换债
            "120", "122", "124", "136", "143", "155",  # 企业债
            "201", "202", "203", "204",  # 国债回购
            "5",  # 基金
            "6",  # A股
            "7",  # 新股
            "9",  # B股
        }

        BJ_SECURITY_PREFIXES = {
            "4",
            "8"
        }

        if not symbol:
            return StockExchange.UNKNOWN

        if len(symbol) == 5:
            return StockExchange.HKEX  # 港股

        # 检查前缀（1位和3位）
        prefixes = {symbol[:1], symbol[:3]}

        if prefixes & SH_SECURITY_PREFIXES:
            return StockExchange.SSE  # 上交所

        if prefixes & BJ_SECURITY_PREFIXES:
            return StockExchange.BSE  # 北交所

        return StockExchange.SZSE  # 深交所

    @staticmethod
    def to_board(symbol, name):
        """
        根据股票代码和名称判断所属板块

        Args:
            symbol (str): 股票代码（如 "300001", "688001"）
            name (str): 股票名称（如 "创业板ETF", "ST平安"）

        Returns:
            StockBoard: 股票所属板块枚举
        """
        # 判断是否创业板（代码 300 开头或名称含"创业板"）
        if symbol.startswith("300") or name.startswith("创业板"):
            return StockBoard.CHINEXT

        # 判断是否科创板（代码 688 开头）
        if symbol.startswith("688"):
            return StockBoard.STAR

        # 判断是否ST股（名称匹配 ST/*ST/SST/S*ST）
        if re.match(r"^(ST|\*ST|SST|S\*ST)", name.upper()):
            return StockBoard.ST

        # 默认返回主板
        return StockBoard.MAIN_BOARD
