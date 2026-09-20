"""Compare instants as instants while retaining uncertain source date precision."""
import calendar
import datetime as dt
import re
from .errors import ApiError

UTC=dt.timezone.utc


def bounds(value):
    try:
        if re.fullmatch(r'\d{4}',value):
            start=dt.datetime(int(value),1,1,tzinfo=UTC);end=dt.datetime(int(value),12,31,23,59,59,999999,tzinfo=UTC)
        elif re.fullmatch(r'\d{4}-\d{2}',value):
            year,month=map(int,value.split('-'));start=dt.datetime(year,month,1,tzinfo=UTC)
            end=dt.datetime(year,month,calendar.monthrange(year,month)[1],23,59,59,999999,tzinfo=UTC)
        elif re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
            start=dt.datetime.fromisoformat(value).replace(tzinfo=UTC);end=start+dt.timedelta(days=1,microseconds=-1)
        else:
            start=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            if start.tzinfo is None:raise ValueError('instant needs timezone')
            start=start.astimezone(UTC);end=start
        return start,end
    except (ValueError,TypeError,OverflowError):
        raise ApiError(400,'invalid_time','时间必须包含明确精度；精确时刻须包含时区')


def in_range(value,since=None,until=None):
    if not value:return False
    start,end=bounds(value)
    return (not since or end>=bounds(since)[0]) and (not until or start<=bounds(until)[1])
