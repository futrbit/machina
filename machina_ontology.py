"""
Machina Technology Ontology

This file defines technology concepts and their aliases.
It does NOT decide what is trending.

The intelligence engine measures the concepts against the corpus.
"""

CONCEPT_FAMILIES = {

    "artificial_intelligence": {
        "label": "Artificial Intelligence",
        "aliases": [
            "artificial intelligence",
            "ai",
            "ai technology",
            "ai system",
            "ai systems",
            "ai tool",
            "ai tools",
            "ai software"
        ]
    },

    "generative_ai": {
        "label": "Generative AI",
        "aliases": [
            "generative ai",
            "generative artificial intelligence",
            "ai model",
            "ai models",
            "generative model",
            "generative models",
            "foundation model",
            "foundation models"
        ]
    },

    "language_models": {
        "label": "Language Models",
        "aliases": [
            "language model",
            "language models",
            "large language model",
            "large language models",
            "llm",
            "llms",
            "vision language model",
            "vision-language model"
        ]
    },

    "ai_agents": {
        "label": "AI Agents",
        "aliases": [
            "ai agent",
            "ai agents",
            "artificial intelligence agent",
            "artificial intelligence agents",
            "autonomous agent",
            "autonomous agents",
            "ai assistant",
            "ai assistants"
        ]
    },

    "machine_learning": {
        "label": "Machine Learning",
        "aliases": [
            "machine learning",
            "machine-learning",
            "deep learning",
            "deep-learning",
            "neural network",
            "neural networks",
            "machine learning model",
            "machine learning models"
        ]
    },

    "computer_vision": {
        "label": "Computer Vision",
        "aliases": [
            "computer vision",
            "computer-vision",
            "machine vision",
            "visual recognition",
            "image recognition",
            "vision system",
            "vision systems"
        ]
    },

    "training_data": {
        "label": "AI Training & Data",
        "aliases": [
            "training data",
            "training dataset",
            "training datasets",
            "ai training data",
            "model training",
            "training models",
            "inference"
        ]
    },

    "autonomous_vehicles": {
        "label": "Autonomous Vehicles",
        "aliases": [
            "autonomous vehicle",
            "autonomous vehicles",
            "autonomous driving",
            "self driving",
            "self-driving",
            "self driving vehicle",
            "self-driving vehicle",
            "driverless vehicle",
            "driverless vehicles",
            "vehicle autonomy"
        ]
    },

    "robotaxis": {
        "label": "Robotaxis",
        "aliases": [
            "robotaxi",
            "robotaxis",
            "robotaxi service",
            "autonomous taxi",
            "autonomous taxis",
            "driverless taxi",
            "driverless taxis"
        ]
    },

    "robotics": {
        "label": "Robotics",
        "aliases": [
            "robotics",
            "robotic system",
            "robotic systems",
            "robot",
            "robots",
            "humanoid robot",
            "humanoid robots",
            "humanoid robotics",
            "industrial robot",
            "industrial robots"
        ]
    },

    "drones": {
        "label": "Drones",
        "aliases": [
            "drone",
            "drones",
            "uav",
            "uavs",
            "unmanned aerial vehicle",
            "unmanned aerial vehicles",
            "drone technology",
            "drone technologies"
        ]
    },

    "drone_delivery": {
        "label": "Drone Delivery",
        "aliases": [
            "drone delivery",
            "drone deliveries",
            "delivery drone",
            "delivery drones",
            "autonomous drone delivery"
        ]
    },

    "drone_autonomy": {
        "label": "Autonomous Drones",
        "aliases": [
            "autonomous drone",
            "autonomous drones",
            "drone autonomy",
            "autonomous uav",
            "autonomous uavs"
        ]
    },

    "semiconductors": {
        "label": "Semiconductors",
        "aliases": [
            "semiconductor",
            "semiconductors",
            "chip",
            "chips",
            "ai chip",
            "ai chips",
            "gpu",
            "gpus",
            "processor",
            "processors"
        ]
    },

    "quantum_computing": {
        "label": "Quantum Computing",
        "aliases": [
            "quantum computing",
            "quantum computer",
            "quantum computers",
            "quantum computing system",
            "quantum processor",
            "quantum processors"
        ]
    },

    "cybersecurity": {
        "label": "Cybersecurity",
        "aliases": [
            "cybersecurity",
            "cyber security",
            "cyber attack",
            "cyber attacks",
            "cyber threat",
            "cyber threats"
        ]
    },

    "electric_vehicles": {
        "label": "Electric Vehicles",
        "aliases": [
            "electric vehicle",
            "electric vehicles",
            "ev",
            "evs",
            "electric car",
            "electric cars"
        ]
    },

    "space_technology": {
        "label": "Space Technology",
        "aliases": [
            "space technology",
            "space technology",
            "satellite",
            "satellites",
            "spacecraft",
            "spacecrafts"
        ]
    }
}


def build_alias_lookup():
    lookup = {}

    for concept_id, concept in CONCEPT_FAMILIES.items():
        for alias in concept["aliases"]:
            lookup[alias.lower()] = concept_id

    return lookup
