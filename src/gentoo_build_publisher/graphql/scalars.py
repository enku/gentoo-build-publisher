"""custom scalars for the GraphQL schema"""

import datetime as dt

from ariadne import ScalarType

datetime_scalar = ScalarType("DateTime")


@datetime_scalar.serializer
def serialize_datetime(value: dt.datetime) -> str:
    """Serialize the datetime value to ISO format"""
    return value.isoformat()
