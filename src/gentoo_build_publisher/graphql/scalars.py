"""custom scalars for the GraphQL schema"""

import datetime as dt

from ariadne import ScalarType

date_scalar = ScalarType("Date")
datetime_scalar = ScalarType("DateTime")


@date_scalar.serializer
def serialize_date(value: dt.date) -> str:
    """Serialize the date value to ISO format"""
    return value.isoformat()


@date_scalar.value_parser
def parse_date_value(value: str) -> dt.date:
    """Deserialize ISO-formatted date"""
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid Date") from None


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
