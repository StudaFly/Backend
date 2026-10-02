"""Reference data shared by every client (labels, choices).

The backend is the single source of truth: the web and mobile apps render these
lists instead of hard-coding their own copies. Keys match the API enums.
"""

MOBILITY_TYPES = [
    {"key": "erasmus", "label": "Erasmus", "description": "Échange universitaire européen"},
    {"key": "stage", "label": "Stage", "description": "Stage en entreprise à l'étranger"},
    {
        "key": "semestre",
        "label": "Semestre",
        "description": "Semestre dans une université partenaire",
    },
    {
        "key": "double_diplome",
        "label": "Double diplôme",
        "description": "Programme de double diplôme",
    },
]

TASK_CATEGORIES = [
    {"key": "admin", "label": "Admin"},
    {"key": "finance", "label": "Finance"},
    {"key": "health", "label": "Santé"},
    {"key": "housing", "label": "Logement"},
    {"key": "practical", "label": "Pratique"},
]

TASK_PRIORITIES = [
    {"value": 1, "label": "Haute"},
    {"value": 2, "label": "Moyenne"},
    {"value": 3, "label": "Basse"},
]

AVATAR_EMOJIS = ["🎓", "✈️", "🌍", "📚", "🏃", "🎨", "🎸", "🍕", "🌊", "🦁"]

CATEGORY_LABELS = {c["key"]: c["label"] for c in TASK_CATEGORIES}
