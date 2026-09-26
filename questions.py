"""Question banks. Interview-mode questions double as the syllabus the
candidate is drilling (they mirror the fin-research-agent interview bank,
docs/07 there). Server walks the bank in order; the LLM only polishes.

Add/edit freely — the interviewer picks up changes on next start.
"""

AI_ENGINEER = [
    "Walk me through a RAG pipeline you would build, end to end.",
    "How do you decide chunk size when indexing documents, and how would you know your choice is right?",
    "When does plain vector search fail, and what do you add to fix it?",
    "How do you evaluate a RAG system before shipping it?",
    "Explain recall at k versus MRR — when does each matter?",
    "What is LLM-as-judge, and how do you stop it from being unreliable?",
    "How do you prevent quality regressions after the system is in production?",
    "What is an agent, really, and when would you not use one?",
    "How do you keep an agent from looping forever or burning money?",
    "How do you get reliable structured output from an LLM?",
    "How should your system behave when it does not know the answer?",
    "A document you retrieved contains instructions like 'ignore previous directions' — what happens in your system?",
    "How would you stream an LLM response to a browser?",
    "Walk me through your caching strategy for an LLM product.",
    "How do you track and reduce cost per query?",
    "Fine-tuning versus RAG versus prompting — how do you decide?",
    "What is LoRA and why is it cheap compared to full fine-tuning?",
    "What are embeddings, and what breaks if you switch embedding models?",
    "Finally: why should we hire you as an AI engineer?",
]

BEHAVIORAL = [
    "Tell me about yourself.",
    "Tell me about a time you disagreed with a teammate on a technical decision.",
    "Describe the hardest bug you have debugged and how you found it.",
    "Tell me about a deadline you almost missed. What did you do?",
    "Describe a time you received harsh feedback. What changed?",
    "Tell me about a project you drove without being asked.",
    "How did you explain a complex technical decision to a non-technical stakeholder?",
    "Tell me about a time you had to say no to a requirement.",
    "Describe a mistake you made in production and what you changed after.",
    "What is the most complex system you have owned end to end?",
    "Why do you want to move into AI engineering after three years as an SDE?",
    "Where do you want to be in two years?",
]

DAILY_STARTERS = [
    "How is your day going so far?",
    "What did you work on today?",
    "Tell me about your weekend plans.",
    "What is something interesting you read or watched recently?",
    "If you had a free month to build anything, what would you build?",
    "Teach me something you know well, in simple words.",
    "What is your favorite food to cook or order, and why?",
    "Describe your ideal workday, hour by hour.",
    "What is one thing in tech you are excited about right now?",
    "Explain your main project to me as if I were your grandmother.",
]
