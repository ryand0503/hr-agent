import json
import anthropic
import config


def rank_candidates(jd_text, candidates, top_n):
    """
    Send all candidate CV texts + JD to Claude and get back ranked results.
    Returns a list of dicts with rank, score, summary, strengths, gaps.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Build a numbered list of candidates for the prompt
    candidates_block = ""
    for i, c in enumerate(candidates, 1):
        cv_snippet = (c["cv_text"] or "")[:3000]  # cap per candidate to control token usage
        candidates_block += f"\n--- CANDIDATE {i} (ID: {c['id']}, Name: {c['name']}) ---\n{cv_snippet}\n"

    prompt = f"""You are an expert HR recruiter. Your task is to rank candidates for a job position.

JOB DESCRIPTION:
{jd_text}

CANDIDATES:
{candidates_block}

Instructions:
- Rank ALL candidates from most to least suitable for the job description above.
- Return only the TOP {top_n} candidates.
- For each candidate return a JSON object with these fields:
  - "candidate_id": the ID shown above
  - "name": candidate name
  - "rank": their rank (1 = best fit)
  - "score": suitability score out of 100
  - "summary": 2-sentence summary of why they fit or don't fit
  - "strengths": top 3 strengths relevant to this role (as a short string)
  - "gaps": top 2 gaps or missing requirements (as a short string)

Return ONLY a valid JSON array of {top_n} objects. No extra text before or after the JSON.
"""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    results = json.loads(raw)

    # Attach DB candidate id properly
    id_map = {c["id"]: c for c in candidates}
    enriched = []
    for r in results:
        cid = r.get("candidate_id")
        candidate = id_map.get(cid, {})
        enriched.append({
            "id": cid,
            "name": r.get("name", candidate.get("name", "Unknown")),
            "rank": r.get("rank"),
            "score": r.get("score"),
            "summary": r.get("summary", ""),
            "strengths": r.get("strengths", ""),
            "gaps": r.get("gaps", ""),
            "email": candidate.get("email", ""),
        })

    enriched.sort(key=lambda x: x["rank"])
    return enriched
