"""Character questions (REQ-049): the uncomfortable, about-the-person questions
real interviewers ask on purpose — not about the job's skills, but about
self-awareness, ownership and composure. A fixed, reviewed bank (no LLM), so
the copy is ours and the same in every session. Code picks 1–2 per session and
rotates them across sessions (`practice.pick_session_questions`)."""
from __future__ import annotations

# id → (en, es). Order = the family order we rotate through.
CHARACTER_QUESTIONS: dict[str, tuple[str, str]] = {
    "char_wrong_call": (
        "Tell me about a decision of yours that turned out to be wrong. When did you realise it, and what did you do next?",
        "Cuéntame de una decisión tuya que resultó equivocada. ¿Cuándo te diste cuenta y qué hiciste después?",
    ),
    "char_pushback": (
        "Tell me about a time a colleague or manager strongly disagreed with you. How did that conversation go?",
        "Cuéntame de una vez en que un colega o tu jefe estuvo muy en desacuerdo contigo. ¿Cómo fue esa conversación?",
    ),
    "char_hard_feedback": (
        "What's the hardest feedback you've received at work, and what did you change because of it?",
        "¿Cuál es el comentario más difícil que has recibido en el trabajo, y qué cambiaste a raíz de él?",
    ),
    "char_priorities": (
        "Tell me about a time two people needed opposite things from you at the same time. How did you decide?",
        "Cuéntame de una vez en que dos personas necesitaban de ti cosas opuestas al mismo tiempo. ¿Cómo decidiste?",
    ),
    "char_message": (
        "Tell me about a time you struggled to get your message across to someone. What did you try, and what finally worked?",
        "Cuéntame de una vez en que te costó hacerte entender con alguien. ¿Qué intentaste y qué funcionó al final?",
    ),
    "char_growth": (
        "What's one area you're actively working to improve right now, and what are you doing about it?",
        "¿Qué aspecto tuyo estás trabajando para mejorar ahora mismo, y qué estás haciendo al respecto?",
    ),
    "char_deadline_slip": (
        "Tell me about a time you made a mistake under a tight deadline. What happened, and how did you handle it?",
        "Cuéntame de una vez en que cometiste un error con una fecha límite encima. ¿Qué pasó y cómo lo manejaste?",
    ),
    "char_comfort_zone": (
        "Tell me about a moment at work that pushed you out of your comfort zone. What did you do with it?",
        "Cuéntame de un momento en el trabajo que te sacó de tu zona de confort. ¿Qué hiciste con eso?",
    ),
    "char_restart": (
        "Tell me about a time the plan changed halfway through and your work had to start over. How did you handle it?",
        "Cuéntame de una vez en que el plan cambió a mitad de camino y tu trabajo tuvo que empezar de nuevo. ¿Cómo lo manejaste?",
    ),
}


def character_question(qid: str, lang: str) -> dict:
    """One bank entry as a session question dict (same shape as toolkit ones)."""
    en, es = CHARACTER_QUESTIONS[qid]
    return {"id": qid, "text": es if lang == "es" else en, "type": "character",
            "competency_id": None}
