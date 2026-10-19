# Design decisions

Short notes on the main trade-offs, for anyone reviewing the code.

**1. Accuracy over completeness.** A partial report that is right beats a complete one that has to be re-checked line by line. Anything the sources don't support goes under "Unverified leads" or "Information gaps"; nothing is filled in by guessing.

**2. Citation numbers are assigned by code, not written by the model.** The research call returns text blocks with citations attached by the API, each with a URL and a short quote from the page. Each cited block becomes a *claim* with its evidence. The second call may only refer to claim IDs; the code turns those IDs into `[n]` numbers. The model therefore cannot invent a citation number or point one at the wrong page, and a bullet with no valid claim ID is dropped before it reaches the report.

**3. An automatic check pass instead of a review form.** The second call compares each claim with its quoted evidence before writing. Claims the quote doesn't support are moved to "Unverified leads" with a reason. The person checks the finished Word file, where each numbered source lists the exact text quoted from it, so checking a fact means reading a line, not searching again.

**4. Basic web search tool (`web_search_20250305`).** Newer versions filter results with code first, which saves tokens but adds a layer between the page and the citation. Traceability matters more here than token cost.

**5. Clues identify the company; the person is not researched.** Contact details (email domain, phone prefix, job title) are used to find and confirm the right company, especially small firms with a thin web presence. Testing showed that a prompt instruction alone wasn't enough, because a personal LinkedIn page was used as a source. Personal profile pages (`linkedin.com/in`) are now blocked in the search tool itself, and the check step refers to people other than the named contact by role.

**6. One provider for now, isolated in one file.** All API code lives in `research/claude_client.py`, which returns plain data classes. Another provider would be a second client with the same two methods. It was left out on purpose: the evidence quotes that the check pass relies on come from the Anthropic citation format.

**7. A fixed reference-sheet layout.** Every report has the same key-facts table (what they do, business type, location, registration, customers, size, identity check), with "Not found" where nothing was confirmed. Reports for different companies can then be compared, and missing information is visible at a glance. Sources go last in small print, which brought a test report down from seven pages to under two.

**8. Claims are whole sentences.** The API often attaches a citation to part of a sentence ("incorporated in 2014"). On its own, that fragment can't be checked or understood, so each claim is widened to the full sentence it sits in.

**9. A flat structured-output schema.** The check step returns JSON that must match a schema. A nested version (one object per key fact) was rejected by the API as too complex. The model now returns flat rows (`section`, `label`, `text`, `claim_ids`), and the code sorts them into the report.
