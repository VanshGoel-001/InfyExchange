from enum import Enum


class UserRole(str, Enum):
    SE = "SE"
    DSE = "DSE"
    SP_L1 = "SP_L1"
    SP_L2 = "SP_L2"


class ListingType(str, Enum):
    SELL = "SELL"
    RENT = "RENT"
    LEND = "LEND"
    GIVEAWAY = "GIVEAWAY"


class ListingCategory(str, Enum):
    BADMINTON = "BADMINTON"
    TABLE_TENNIS = "TABLE_TENNIS"
    POOL_SNOOKER = "POOL_SNOOKER"
    SQUASH = "SQUASH"
    TENNIS = "TENNIS"
    CRICKET = "CRICKET"
    FOOTBALL = "FOOTBALL"
    BASKETBALL = "BASKETBALL"
    OTHER = "OTHER"


class ItemCondition(str, Enum):
    NEW = "NEW"
    LIKE_NEW = "LIKE_NEW"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


class ListingStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SOLD = "SOLD"
    RENTED = "RENTED"
    UNAVAILABLE = "UNAVAILABLE"


class InterestStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class NeedType(str, Enum):
    BUY = "BUY"
    RENT = "RENT"
    BORROW = "BORROW"


class NeedStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FULFILLED = "FULFILLED"
    CLOSED = "CLOSED"