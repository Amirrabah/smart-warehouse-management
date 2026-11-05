from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


Paging = Annotated[PageParams, Depends(page_params)]


class Page[T](BaseModel):
    """One page of a list, plus how many items match in total (for 'page 2 of 9')."""

    items: list[T]
    total: int
