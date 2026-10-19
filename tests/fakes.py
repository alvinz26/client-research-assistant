"""Small stand-ins for Anthropic API response objects (attribute access only)."""
from types import SimpleNamespace as NS


def query(q):
    return NS(type="server_tool_use", name="web_search", input={"query": q})


def results(*items):
    return NS(type="web_search_tool_result",
              content=[NS(type="web_search_result", url=u, title=t, page_age=a, encrypted_content="x") for u, t, a in items])


def text(body, *cites):
    return NS(type="text", text=body, citations=[
        NS(type="web_search_result_location", url=u, title=t, cited_text=q, encrypted_index="x") for u, t, q in cites] or None)


def response(blocks, stop="end_turn", searches=0):
    usage = NS(input_tokens=1000, output_tokens=200, server_tool_use=NS(web_search_requests=searches))
    return NS(content=blocks, stop_reason=stop, usage=usage, stop_details=None)
