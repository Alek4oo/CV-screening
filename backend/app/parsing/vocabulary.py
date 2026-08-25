"""Речници за парсване на CV — заглавия на секции и разпознавани умения.

Съзнателно плосък списък, а не онтология: целта е предвидимо и обяснимо
разпознаване, което рекрутерът може да провери с очи.
"""

# Канонично име → варианти, които срещаме в текста (в долен регистър).
SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "python": ("python", "питон"),
    "java": ("java",),
    "javascript": ("javascript", "js"),
    "typescript": ("typescript", "ts"),
    "c#": ("c#", "c sharp", ".net", "dotnet"),
    "c++": ("c++",),
    "go": ("golang",),
    "php": ("php",),
    "ruby": ("ruby",),
    "sql": ("sql",),
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
    "mongodb": ("mongodb", "mongo"),
    "redis": ("redis",),
    "elasticsearch": ("elasticsearch",),
    "django": ("django",),
    "flask": ("flask",),
    "fastapi": ("fastapi",),
    "spring": ("spring", "spring boot"),
    "react": ("react", "reactjs", "react.js"),
    "angular": ("angular",),
    "vue": ("vue", "vuejs", "vue.js"),
    "node.js": ("node.js", "nodejs", "node js"),
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure",),
    "gcp": ("gcp", "google cloud"),
    "terraform": ("terraform",),
    "linux": ("linux",),
    "git": ("git",),
    "ci/cd": ("ci/cd", "cicd", "continuous integration"),
    "rest": ("rest api", "restful", "rest"),
    "graphql": ("graphql",),
    "kafka": ("kafka",),
    "rabbitmq": ("rabbitmq",),
    "pandas": ("pandas",),
    "numpy": ("numpy",),
    "pytorch": ("pytorch",),
    "tensorflow": ("tensorflow",),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "machine learning": ("machine learning", "машинно обучение"),
    "pytest": ("pytest",),
    "agile": ("agile", "scrum"),
}

# Заглавия на секции. Редът няма значение — търси се съвпадение по подниз.
SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "skills": (
        "умения",
        "технически умения",
        "технологии",
        "компетенции",
        "skills",
        "technical skills",
        "core skills",
        "technologies",
    ),
    "experience": (
        "опит",
        "професионален опит",
        "трудов опит",
        "трудов стаж",
        "работен опит",
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
    ),
    "education": (
        "образование",
        "образование и квалификация",
        "qualifications",
        "education",
        "academic background",
    ),
    "languages": (
        "езици",
        "чужди езици",
        "languages",
        "language skills",
    ),
}

# Думи, които издават учебна степен — използват се при разбор на образованието.
DEGREE_KEYWORDS: tuple[str, ...] = (
    "бакалавър",
    "магистър",
    "доктор",
    "специалист",
    "средно образование",
    "гимназия",
    "университет",
    "bachelor",
    "master",
    "phd",
    "msc",
    "bsc",
    "high school",
    "university",
)

# Маркери за "до днес" в диапазон от дати.
PRESENT_MARKERS: tuple[str, ...] = (
    "настоящем",
    "сега",
    "днес",
    "present",
    "current",
    "now",
)
