from typing import Annotated, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class HotelInfo(TypedDict):
    name: str
    price: int
    rating: float
    address: str
    stock: int


class BookingInfo(TypedDict):
    hotel_name: Optional[str]
    check_in: Optional[str]
    check_out: Optional[str]
    guest_name: Optional[str]


class AgentState(TypedDict):
    # add_messages 是累加器，每次不会覆盖而是追加
    messages: Annotated[List, add_messages]
    # 最近一次查询的酒店列表，跨轮次保持
    hotels_list: List[HotelInfo]
    # 预订信息
    booking_info: BookingInfo
    # 意图分类结果
    intents: List[str]
