"""custom scalars for the GraphQL schema"""

import datetime as dt

from ariadne import ScalarType

datetime_scalar = ScalarType("DateTime")


@datetime_scalar.serializer
def serialize_datetime(value: dt.datetime) -> str:
    """Serialize the datetime value to ISO format"""
    return value.isoformat()


@datetime_scalar.value_parser
def parse_datetime_value(value: str) -> dt.datetime:
    """Deserialize ISO-formatted datetime"""
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid DateTime") from None
