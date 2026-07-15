import json
import urllib.request
import urllib.parse
import settings


def build_prompt(jd_text, candidates, top_n):
    candidates_block = ""
    for i, c in enumerate(candidates, 1):
        cv_snippet = (c["cv_text"] or "")[:3000]
        candidates_block += f"\n--- CANDIDATE {i} (ID: {c['id']}, Name: {c['name']}) ---\n{cv_snippet}\n"

    return f"""You are an expert HR recruiter. Your task is to rank candidates for a job position.

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

Return ONLY a valid JSON array of {top_n} objects. No extra text before or after the JSON."""


def parse_response(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def call_claude(prompt, api_key):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def call_local_llm(prompt, base_url, model):
    """Call Ollama or any OpenAI-compatible local LLM."""
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4096,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def rank_candidates(jd_text, candidates, top_n):
    s = settings.load()
    llm_mode = s.get("llm_mode", "claude")
    prompt = build_prompt(jd_text, candidates, top_n)

    if llm_mode == "local":
        base_url = s.get("local_llm_url", "http://host.docker.internal:11434")
        model    = s.get("local_llm_model", "gemma3:1b")
        raw = call_local_llm(prompt, base_url, model)
    else:
        api_key = s.get("anthropic_api_key", "")
        if not api_key:
            raise ValueError("Anthropic API key not set. Go to Settings.")
        raw = call_claude(prompt, api_key)

    results = parse_response(raw)

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
