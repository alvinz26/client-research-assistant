# Design decisions

Short notes on the main trade-offs, for anyone reviewing the code.

**1. Accuracy over completeness.** A partial report that is right beats a complete one that has to be re-checked line by line. Anything the sources don't support goes under "Unverified leads" or "Information gaps"; nothing is filled in by guessing.

**2. Citation numbers are assigned by code, not written by the model.** The research call returns text blocks with citations attached by the API, each with a URL and a short quote from the page. Each cited block becomes a *claim* with its evidence. The second call may only refer to claim IDs; the code turns those IDs into `[n]` numbers. The model therefore cannot invent a citation number or point one at the wrong page, and a bullet with no valid claim ID is dropped before it reaches the report.

**3. An automatic check pass instead of a review form.** The second call compares each claim with its quoted evidence before writing. Claims the quote doesn't support are moved to "Unverified leads" with a reason. The person checks the finished Word file, where each numbered source lists the exact text quoted from it, so checking a fact means reading a line, not searching again.

**4. Basic web search tool (`web_search_20250305`).** Newer versions filter results with code first, which saves tokens but adds a layer between the page and the citation. Traceability matters more here than token cost.

**5. Clues identify the company; the person is not researched.** Contact details (email domain, phone prefix, job title) are used to find and confirm the right company, especially small firms with a thin web presence. The prompts tell Claude not to profile the individual.

**6. One provider for now, isolated in one file.** All API code lives in `research/claude_client.py`, which returns plain data classes. Another provider would be a second client with the same two methods. It was left out on purpose: the evidence quotes that the check pass relies on come from the Anthropic citation format.

**7. Fixed report sections.** Every report has the same headings, so reports for different companies can be compared and missing information is visible.
