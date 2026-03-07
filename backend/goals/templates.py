"""Pre-built goal templates for ZugaLife.

Each template has a key, title, description, suggested milestones,
and habit names that match the preset habits in habits/routes.py.
"""

GOAL_TEMPLATES: dict[str, dict] = {
    "get_healthier": {
        "title": "Get Healthier",
        "description": "Build sustainable health habits — exercise, nutrition, sleep, and hydration.",
        "suggested_habits": ["Exercise", "Water", "Sleep", "Healthy Eating"],
        "milestones": [
            "Exercise 3+ days per week consistently",
            "Drink 8 glasses of water daily",
            "Sleep 7-8 hours per night",
            "Establish a balanced meal routine",
        ],
    },
    "build_mindfulness": {
        "title": "Build a Mindfulness Practice",
        "description": "Develop a daily mindfulness routine through meditation, gratitude, and screen boundaries.",
        "suggested_habits": ["Meditation", "Gratitude", "No Screens Before Bed"],
        "milestones": [
            "Meditate 5+ minutes daily for a week",
            "Write 3 gratitude entries per week",
            "No screens 30 min before bed for a week",
            "Complete a 10-minute meditation",
        ],
    },
    "read_more": {
        "title": "Read More",
        "description": "Build a consistent reading habit and expand your knowledge.",
        "suggested_habits": ["Reading"],
        "milestones": [
            "Read 20+ minutes daily for a week",
            "Finish your first book",
            "Read 3 books total",
            "Read 30+ minutes daily consistently",
        ],
    },
    "sleep_better": {
        "title": "Sleep Better",
        "description": "Improve sleep quality through consistent routines and healthy habits.",
        "suggested_habits": ["Sleep", "No Screens Before Bed", "Meditation"],
        "milestones": [
            "Set a consistent bedtime for a week",
            "No screens 1 hour before bed",
            "Average 7+ hours of sleep per night",
            "Wake up without an alarm consistently",
        ],
    },
    "reduce_stress": {
        "title": "Reduce Stress",
        "description": "Manage stress through mindfulness, exercise, and intentional relaxation.",
        "suggested_habits": ["Meditation", "Exercise", "Gratitude"],
        "milestones": [
            "Identify your top 3 stress triggers",
            "Meditate when stressed instead of reacting",
            "Exercise 3+ times per week",
            "Practice daily gratitude for 2 weeks",
        ],
    },
    "build_discipline": {
        "title": "Build Daily Discipline",
        "description": "Create structure and consistency in your daily routine.",
        "suggested_habits": ["Sleep", "Exercise", "Reading", "Water"],
        "milestones": [
            "Complete all daily habits for 3 days straight",
            "Maintain a 7-day streak on any habit",
            "Complete all daily habits for a full week",
            "Maintain a 30-day streak on any habit",
        ],
    },
}
