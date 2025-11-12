import os
import logging


logger = logging.getLogger(__name__)


def get_ai_explanation(topic: str) -> str:
    """
    Return a short educational paragraph about why the topic in e-waste is harmful.
    Uses Google Gemini via google-generativeai when a GEMINI_API_KEY/GOOGLE_API_KEY is set.
    Tries multiple model names for compatibility. Falls back to a friendly static message if not configured.
    """
    prompt = (
        f"Explain why {topic} in electronic waste is harmful to human health and the environment "
        f"in 3–4 sentences. Keep it clear and beginner-friendly."
    )

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if gemini_key:
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=gemini_key)
            # 1) Try explicit env model if provided
            explicit_model = os.getenv("GEMINI_MODEL")
            if explicit_model:
                try:
                    model = genai.GenerativeModel(explicit_model)
                    resp = model.generate_content(prompt)
                    text = getattr(resp, "text", None) or (
                        resp.candidates[0].content.parts[0].text if getattr(resp, "candidates", None) else ""
                    )
                    if (text or "").strip():
                        return text.strip()
                except Exception as inner_e:
                    logger.warning("Gemini model %s failed: %s", explicit_model, inner_e)

            # 2) Auto-discover supported text models for this key/account
            try:
                available = list(genai.list_models())
            except Exception as lm_err:
                logger.warning("Gemini list_models failed: %s", lm_err)
                available = []

            # Filter models that support text generation
            def supports_text(m) -> bool:
                methods = set(getattr(m, "supported_generation_methods", []) or [])
                # Newer SDKs use 'generateContent'; accept both variants defensively
                return ("generateContent" in methods) or ("generate_text" in methods)

            candidate_names = [getattr(m, "name", "") for m in available if supports_text(m)]

            # Prefer 1.5 flash/pro variants if present
            preferred_order = [
                "gemini-1.5-flash-002",
                "gemini-1.5-flash-latest",
                "gemini-1.5-pro-002",
                "gemini-1.5-pro-latest",
                "gemini-pro",
            ]

            # Resolve names to actual model ids present in candidate_names (may already include full names)
            ordered_to_try = []
            for preferred in preferred_order:
                # exact match or suffix match if API returns full path like 'models/gemini-1.5-flash-002'
                for cand in candidate_names:
                    if cand == preferred or cand.endswith("/" + preferred):
                        if cand not in ordered_to_try:
                            ordered_to_try.append(cand)
            # add any remaining candidates
            for cand in candidate_names:
                if cand not in ordered_to_try:
                    ordered_to_try.append(cand)

            for model_name in ordered_to_try:
                try:
                    # If API returned names like 'models/xxx', pass as-is; otherwise pass short name
                    model = genai.GenerativeModel(model_name)
                    resp = model.generate_content(prompt)
                    text = getattr(resp, "text", None) or (
                        resp.candidates[0].content.parts[0].text if getattr(resp, "candidates", None) else ""
                    )
                    if (text or "").strip():
                        return text.strip()
                except Exception as inner_e:
                    logger.warning("Gemini model %s failed: %s", model_name, inner_e)
        except Exception as e:
            logger.warning("Gemini init failed: %s", e)

    # Fallback static response
    return (
        "AI key not configured. For demo: Many e-waste components can leach toxic substances like lead, "
        "mercury, and brominated flame retardants. These can contaminate soil and water, harm the nervous "
        "and endocrine systems, and persist in the environment. Always dispose of devices at certified "
        "recycling centers to reduce exposure and enable safe material recovery."
    )


