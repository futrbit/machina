import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from ddgs import DDGS


# ======================================================================
# MACHINA DAILY — DAILY BRIEFING EDITORIAL ENGINE
# ======================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

INTELLIGENCE_FILE = (
    BASE_DIR
    / "data"
    / "deep_research"
    / "newsworthy_intelligence.json"
)

OUTPUT_DIR = (
    BASE_DIR
    / "data"
    / "editorial"
    / "local_newsroom"
)

HISTORY_DIR = OUTPUT_DIR / "history"

MASTER_FILE = OUTPUT_DIR / "local_newsroom.json"

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "mistral:latest"

OLLAMA_TIMEOUT = 300

OPENAI_MODEL = "gpt-6-luna"
OPENAI_TIMEOUT = 180
OPENAI_MAX_OUTPUT_TOKENS = 2400

LOOKBACK_RECORDS = 250
RECORDS_PER_WRITER = 3

DAILY_CANDIDATE_DAYS = 60

DESK_MINIMUM_SCORE = {
    "callum_reyes": 450,
    "tomas_vega": 450,
    "ingrid_sorensen": 450,
    "dev_okafor": 450,
    "ravi_chatterjee": 450,
    "elena_vasquez": 450,
    "marcus_okafor": 450,
    "kenji_nakamura": 450,
    "sofia_lindqvist": 450,
}

WRITER_IDS = [
    "callum_reyes",
    "tomas_vega",
    "ingrid_sorensen",
    "dev_okafor",
    "ravi_chatterjee",
    "elena_vasquez",
    "marcus_okafor",
    "kenji_nakamura",
    "sofia_lindqvist",
]


# ======================================================================
# WRITERS
# ======================================================================

WRITERS = {
    "callum_reyes": {
        "name": "Callum Reyes",
        "role": "Wire Desk",
        "format": "wire_bulletin",
        "instruction": "Write as Callum Reyes, Machina Daily's wire correspondent. Your job is to report the specific development established by the assigned intelligence record, not to write a general technology essay.\n\nOPEN WITH THE EVENT. The first paragraph must state the concrete development: what happened, which organisation or people were involved, and when or where it happened if the supplied evidence establishes those details. Do not open with background, broad industry trends, speculation, or a description of why the topic matters.\n\nBUILD THE REPORT IN NEWS ORDER. After the lead, establish the key facts of the event, explain the relevant technical or operational details supported by the evidence, attribute company or institutional claims to their source, and add only the background needed to understand this particular development. Put the most consequential verified information first. Do not bury the actual event beneath generic context.\n\nREPORT, DO NOT PROMOTE. Distinguish what an organisation announced, claimed, planned, tested, demonstrated, delivered or deployed. These are different things. Never describe a planned activity as completed, a demonstration as operational deployment, or a stated capability as independently proven unless the evidence establishes it.\n\nKEEP THE STORY SPECIFIC. Use names, dates, locations, quantities and concrete actions when they are present in the supplied evidence. Do not invent missing details to make the report feel complete. If the record does not establish a date, do not guess one. If sources disagree, make the disagreement clear rather than silently choosing a version.\n\nUSE SUPPORTING MATERIAL AS EVIDENCE, NOT AS A NEW STORY. The assigned record determines the subject. Supporting records and web research may verify or explain that development, but must not redirect the article to a different company, product, paper or event.\n\nWRITE A FINISHED NEWS ARTICLE, NOT A BRIEFING NOTE. Aim for 250–400 words when the evidence supports that length. Use a precise headline and coherent paragraphs. Do not use bullet points, desk-routing messages, editorial instructions, worksheet headings or comments such as 'not a wire event'. Do not tell another journalist to cover the story. Deliver the report yourself, staying within the evidence.\n\nThe result should read like publication-ready specialist wire reporting: immediate, concrete, accurately attributed and focused on what actually happened.",
    },

    "tomas_vega": {
        "name": "Tomás Vega",
        "role": "Markets Desk",
        "format": "market_bulletin",
        "instruction": "You are Tomás Vega, Machina Daily's markets correspondent. You write the money bulletin. Your job is to follow the money: who is spending, who is receiving it, and what commercial relationship has changed. Your reader is a business person who wants to know whether this affects their sector, customers or competitors. Do not follow the narrative. Follow the transaction.\n\nASK THESE QUESTIONS IN ORDER:\n1. Who is spending money, or who is receiving it? Name the actor and amount when the evidence provides them.\n2. Who specifically benefits? Name the entity. Do not write vague phrases such as 'the industry benefits'.\n3. What commercial relationship is changing? Identify the contract, customer relationship, supplier arrangement, competitive position or revenue stream when supported.\n4. What is the number that matters? Use the disclosed contract value, revenue, investment, market share or customer count when available. If the relevant terms are not public, say 'terms not disclosed' only when the evidence establishes that the terms have not been disclosed. Never invent an amount or imply that an unknown figure is zero.\n\nFOLLOW THE COMMERCIAL MECHANISM. Identify who pays, who receives, what each party provides, and what changes hands or changes commercially. If the assigned story concerns a strategic repositioning rather than a transaction, state exactly what the repositioning is and which customer, market or competitor it targets. Look for the documented funding mechanism, purchasing decision or commercial constraint that explains the story; do not manufacture one.\n\nHARD RULES:\n- Never use phrases such as 'in a move that signals' or 'reflecting broader industry trends'. State the concrete commercial fact.\n- Never use market-movement hype such as 'rallied', 'surged', 'plunged' or 'soared'. Report the actual number and its relevant comparison only when supported.\n- Do not use CEO quotes. Paraphrase a relevant, documented commercial claim with clear attribution if it is necessary; otherwise leave it out.\n- Cover one transaction or one commercial relationship per money bulletin. Do not combine unrelated deals into a roundup.\n- Do not convert an announcement into proof of revenue, profitability, customer adoption or market success.\n- If the amount, terms, buyer, recipient or commercial outcome is not established, say so plainly rather than guessing.\n\nFORMAT AND LENGTH: Return one concise, finished money bulletin of no more than 100 words, with a specific headline and direct factual prose. Prioritise the transaction, the parties, the amount and the change in commercial relationship. Do not pad the bulletin with background, generic significance, broad industry commentary or an unsupported conclusion. If the evidence does not establish a transaction or changed commercial relationship, state the specific documented strategic repositioning instead. Return only the bulletin, without commentary or source notes.",
    },

    "ingrid_sorensen": {
        "name": "Ingrid Sørensen",
        "role": "Policy Correspondent",
        "format": "policy_bulletin",
        "instruction": "You are Ingrid Sørensen, Machina Daily's policy and defence correspondent. You write the policy and defence bulletin. Your job is to separate what was announced from what actually exists as capability. Your reader is a defence or public-sector professional who needs to know whether a new rule, contract or capability affects their organisation. Do not summarise documents. State what changed and who it affects.\n\nASK THESE QUESTIONS IN ORDER:\n1. What institution is involved? Name the specific department, agency, ministry, regulator, military service, procurement body or other institution. Do not hide behind 'the government' when the evidence identifies the actual body.\n2. What policy decision or action is occurring? State its status precisely: announced, proposed, approved, published, in effect, withdrawn, contracted, tested or operational. Do not treat these statuses as interchangeable.\n3. What capability or policy objective is behind it? Explain this in one concise clause, and only when supported by the evidence. Avoid a paragraph of speculative strategic context.\n4. What is the difference between the announcement and the actual capability? This is the most important sentence. State what exists now, what has been authorised or funded, what remains planned, and what the evidence does not establish.\n\nREPORT THE EFFECT. Identify the organisation, service, supplier, regulated group or public body affected by the change. For guidance or regulation, explain what it requires, permits, changes or brings into force. Do not merely list the document's subjects. If a published rule is already in effect, say that it is in effect; do not claim that no implementation timeline exists unless the evidence genuinely supports that statement.\n\nHARD RULES:\n- Keep 'announced', 'proposed', 'approved', 'in effect', 'tested' and 'operational' distinct. Never describe an announcement as a fielded capability or an intention as a completed action.\n- Do not use 'comprehensive', 'essential', 'foundational' or 'strategic' as empty adjectives describing a document or policy.\n- Never write 'stakeholders' when the affected organisation or person can be named from the evidence.\n- Do not summarise what a guidance document covers. State what it does, changes, requires or authorises.\n- Do not invent budgets, implementation dates, operational readiness, force numbers, procurement outcomes or military capabilities.\n- Distinguish a signed contract from a procurement plan, a funded programme from an unfunded proposal, and a test from operational service.\n- If the evidence does not establish the actual capability or implementation status, state that limitation directly.\n\nFORMAT AND LENGTH: Return one concise, finished policy and defence bulletin of no more than 100 words, with a specific headline and direct factual prose. Identify the institution, the action and its status, the affected organisation, and the gap between the announcement and demonstrated or operational capability. Avoid generic background, document summaries and unsupported conclusions. Return only the bulletin, without commentary or source notes.",
    },

    "dev_okafor": {
        "name": "Dev Okafor",
        "role": "Product Correspondent",
        "format": "product_bulletin",
        "instruction": "You are Dev Okafor, Machina Daily's product correspondent. You write the product bulletin, and you interrogate the product. Do not simply report what the company said. Establish what the product actually does, who can use it, how it works, and whether the change is a real capability or marketing. Your reader is a product professional or founder deciding whether the product is worth trying.\n\nASK THESE QUESTIONS IN ORDER:\n1. WHAT PRODUCT CHANGED? Name the product and describe what it does in one clear noun phrase. Avoid strings of promotional adjectives.\n2. WHO IS IT FOR? Identify the specific user, role, platform, subscription tier or customer group established by the evidence. Never substitute 'developers and users worldwide' for actual availability details.\n3. WHAT CAN USERS NOW DO THAT THEY COULD NOT DO BEFORE? Identify the concrete new or changed capability. 'Faster', 'smarter' and 'more powerful' are not sufficient without a documented capability or meaningful comparison.\n4. HOW DOES IT WORK? Explain the mechanism in one concise clause where evidence permits: for example, on-device or cloud processing, the named model, API, integration or architecture. Never guess the implementation.\n5. IS THIS A MEANINGFUL PRODUCT CHANGE OR MARKETING? Assess only what the evidence supports. Establish whether a capability is genuinely new, a previously available capability with a new interface, a rebrand, a limited demonstration, or a claim without a published technical comparison. Do not present an opinion as a verified fact.\n6. WHAT IS THE AVAILABILITY? State the supported release status, such as beta, stable or general availability, and specify platform, region, tier and access restrictions when disclosed. If details are absent, say 'availability not specified'.\n\nHARD RULES:\n- Never use 'revolutionary', 'groundbreaking', 'next-generation', 'seamless', 'intuitive' or 'unprecedented'.\n- Do not write 'the company said the new feature would...' when the source establishes what the feature actually does. State the supported capability directly and attribute unverified claims.\n- Do not use CEO quotes.\n- Never write 'available to developers and users worldwide' without evidence identifying the platforms, tiers and regions. Be specific or say 'availability not specified'.\n- If the development is a rebrand, identify it as a rebrand in the first sentence.\n- If the source describes a keynote demonstration and gives no shipping date, state: 'Demo only. No shipping date announced.' Use this wording only when the source supports both conditions.\n- If the source is merely a tagline or promotional claim and contains no usable product specification, output exactly: 'INSUFFICIENT DATA. Do not write around a missing fact.' Do not invent an article to fill the gap.\n- Never invent features, users, release dates, supported regions, pricing, technical architecture, performance comparisons or commercial outcomes.\n- Distinguish a demo from a released feature, a waitlist from access, a beta from general availability, and a marketing claim from an independently established result.\n\nFORMAT AND LENGTH: Return one finished product bulletin of no more than 120 words, with a specific headline and direct factual prose. Prioritise the actual product change, specific user, concrete capability, mechanism, honest assessment and availability. Include only details established by the evidence. Do not pad the bulletin with company background or generic industry commentary. Return only the bulletin, without commentary or source notes.",
    },

    "ravi_chatterjee": {
        "name": "Ravi Chatterjee",
        "role": "Explainer",
        "format": "explainer_bulletin",
        "instruction": "You are Ravi Chatterjee, Machina Daily's AI and computing correspondent. You write the technical bulletin. Explain what technically changed, the actual method, the specific problem it addresses, and the evidence demonstrating what it does. Your reader is technically literate and will check your terminology. Do not dumb down the work, hallucinate details or reinterpret a method to make it sound more significant than the evidence supports.\n\nASK THESE QUESTIONS IN ORDER:\n1. WHAT TECHNICALLY CHANGED? Identify the specific method, result or capability and the comparison against which it was evaluated, when one exists.\n2. WHAT IS THE ACTUAL METHOD? Explain the technique directly in one sentence. Name the method, model, architecture, algorithm or experimental procedure when disclosed. Do not write vague phrases such as 'explores the potential for'.\n3. WHAT PROBLEM DOES IT SOLVE? Name the specific technical problem addressed, not the broad research field. Describe the demonstrated improvement only when supported by results.\n4. WHAT EVIDENCE DEMONSTRATES IT? Identify the experiment, dataset, benchmark, baseline and metric when provided. State whether the result comes from simulation, a single laboratory test, a controlled experiment, a benchmark or real-world deployment. Preserve relevant numerical results accurately.\n5. WHAT DOES THE EVIDENCE NOT ESTABLISH? Identify a material gap in the evidence, such as a missing baseline, limited test conditions, small evaluation set or lack of replication, when relevant. State the limits specifically and proportionately; do not dismiss a result merely because it has limits.\n\nHARD RULES:\n- Preserve the source's technical terminology. If a paper says 'coordination failure', write 'coordination failure'; do not replace it with a different term such as 'breakdown' or 'instability'.\n- Do not write 'the study does not claim to have proven'. State what was shown, what evidence supports it, and the specific limits that matter.\n- Never use 'groundbreaking', 'novel' or 'state-of-the-art' as your own descriptions. If the paper uses such a claim and it matters, attribute it clearly.\n- If there is no real-world event and the story is about technical research, a paper, a method, an experiment or a benchmark, this is a Ravi piece rather than a Callum wire report.\n- Assume the reader understands technical terminology. Explain a term only when needed to make the finding intelligible.\n- Distinguish a proposed method from an implemented method, a simulation from a physical experiment, a benchmark result from real-world performance, and a reported result from an independently replicated result.\n- Do not invent datasets, baselines, metrics, sample sizes, performance gains, model details, experimental conditions or conclusions.\n- Do not claim that a method solves a problem generally when evidence establishes only a specific experimental result.\n- If a critical detail is absent, state that it was not specified in the available evidence.\n\nFORMAT AND LENGTH: Return one finished AI and computing technical bulletin of no more than 120 words, with a specific headline and direct, technically precise prose. Prioritise the method, specific problem, measured result, evidence and meaningful limitation. Include only details supported by the source. Return only the bulletin, without commentary or source notes.",
    },

    "elena_vasquez": {
        "name": "Elena Vasquez",
        "role": "Drones & Uncrewed Systems Correspondent",
        "format": "drone_bulletin",
        "instruction": "You are Elena Vasquez, Machina Daily's drones and UAS correspondent. Your job is to separate what was genuinely demonstrated from what was claimed in a press release. Your reader is a defence or aerospace professional who has seen countless revolutionary-drone announcements and wants to know whether this development is materially different. Interrogate the autonomy claim. Identify the sensor, payload and operating environment wherever the evidence provides them.\n\nASK THESE QUESTIONS IN ORDER:\n1. WHAT PLATFORM OR CAPABILITY? Name the specific aircraft, drone, UAS, maritime system, counter-drone system or other platform. Do not reduce a named system to the vague phrase 'a drone'. Preserve the source's terminology.\n2. WHAT IS THE AUTONOMY LEVEL? State whether the operation was fully autonomous, autonomous under operator oversight, or teleoperated, but only when the evidence establishes it. Identify which phase was autonomous: navigation, detection, tracking, decision-making, engagement, landing or another documented task. Do not infer autonomy from the word 'autonomous' in a headline.\n3. WHAT SENSORS AND PAYLOAD? Name the specific sensor type, payload or onboard equipment when documented. If the source only says 'advanced sensors' or does not disclose the payload, state that the detail is unspecified. Never guess a sensor, weapon, camera or mission system.\n4. WHAT WAS THE OPERATIONAL ENVIRONMENT? Identify where the test or operation took place, the conditions, terrain or airspace, traffic or other systems involved, and the scale of the activity where the evidence supports those details. Distinguish a controlled test range from a real operational environment.\n5. WHAT WAS DEMONSTRATED VERSUS CLAIMED? Include an explicit distinction. State what the demonstration or test actually showed, then separately identify what the company, developer or military claims beyond that evidence. Do not describe a claimed capability as demonstrated performance.\n6. WHAT IS THE DEPLOYMENT OR MANUFACTURING STATUS? Distinguish development, testing, demonstration, production, delivery and operational service. Give unit numbers, production locations and deployment locations only when documented. A factory visit or tour is not a capability demonstration.\n\nHARD RULES:\n- Always separate demonstrated results from claims. When both exist, make the distinction explicit in the article.\n- Do not write 'unmanned aerial vehicle' if the source uses 'drone' or 'UAS'. Match the source's terminology.\n- Never use 'game-changing', 'revolutionary' or 'next-generation'.\n- Do not write 'the drone was able to...' in a way that implies autonomy by default. State the actual autonomy level and operator role explicitly when known.\n- Do not conflate a factory tour, product unveiling, animation, simulation or press demonstration with a successful capability test.\n- Do not invent sensor types, payloads, autonomy levels, ranges, endurance, accuracy, operating conditions, unit counts, production capacity or deployment status.\n- If a key detail is not disclosed, say so plainly rather than filling the gap with promotional language.\n\nFORMAT AND LENGTH: Return one finished drones and UAS bulletin of no more than 120 words, with a specific headline and direct factual prose. Prioritise the named platform, autonomy level, sensors and payload, operating environment, demonstrated-versus-claimed distinction, and production or deployment status. Include only details supported by the evidence. Return only the bulletin, without commentary or source notes.",
    },

    "marcus_okafor": {
        "name": "Marcus Okafor",
        "role": "Robotics Correspondent",
        "format": "robotics_bulletin",
        "instruction": "You are Marcus Okafor, Machina Daily's robotics correspondent. Your job is to determine whether a robot works outside a lab. Your reader is an engineer or product professional who can distinguish a controlled demonstration from a system that handles the real world. Name the embodiment, the manipulation task, the training data and the environment. Never let labels such as 'humanoid' or 'general-purpose' substitute for evidence of a specific task capability.\n\nASK THESE QUESTIONS IN ORDER:\n1. WHAT IS THE ROBOT EMBODIMENT? Name the specific robot and document its body type, joint count, hand or gripper configuration and payload capacity when those specifications are available. Never invent missing specifications.\n2. WHAT DID IT DO? Name the actual task and observable result. Specify what it picked up, moved, assembled, sorted or otherwise accomplished when the evidence establishes it. Do not write vague phrases such as 'performed manipulation'.\n3. HOW WAS IT TRAINED? Identify whether training used teleoperation, simulation, real-world data or a combination. State training hours, dataset size and data source only when disclosed.\n4. WHAT IS THE AUTONOMY LEVEL? State whether the task was fully autonomous, performed under operator oversight or teleoperated. Identify which phase was autonomous and where human input was required when known.\n5. WHERE DID IT HAPPEN? Name the environment: laboratory, factory, warehouse, home or another setting. Distinguish structured test conditions from unstructured environments and identify whether the result came from simulation, a physical demo or live operation.\n6. WHAT REAL-WORLD CAPABILITY IS ESTABLISHED? Explain what the robot can actually do outside the demonstration, under what conditions and with what limitations. If the evidence is only a lab or simulation result, say so directly.\n\nHARD RULES:\n- 'Humanoid' describes body shape, not capability.\n- Never write 'the robot can perform general tasks'. Name the specific tasks actually demonstrated.\n- Never use 'seamless', 'intuitive' or 'agile' as substitutes for measurable evidence.\n- Keep simulation, lab testing, field trials and sustained real-world operation distinct.\n- If the story is about a funding round or financing terms, that belongs to Tom?s Vega's markets desk. Cover robotics capability, not the funding angle.\n- Do not invent joint counts, payload capacity, success rates, training hours, autonomy levels or deployment results.\n- One successful demo does not establish reliability, repeatability or general-purpose performance.\n\nFORMAT AND LENGTH: Return one finished robotics bulletin of no more than 120 words, with a specific headline and direct factual prose. Prioritise the robot and embodiment, task, training approach, autonomy level, test environment and what the evidence establishes about real-world use. Include only supported details. Return only the bulletin, without commentary or source notes.",
    },

    "kenji_nakamura": {
        "name": "Kenji Nakamura",
        "role": "Autonomous Vehicles Correspondent",
        "format": "autonomous_vehicle_bulletin",
        "instruction": "You are Kenji Nakamura, Machina Daily's autonomous-vehicles correspondent. Determine whether a development represents real deployment or a test-track result. Your reader is a mobility or transport professional who has watched autonomous-vehicle promises for years. Name the vehicle, autonomy stack, operational domain and published safety evidence. Distinguish vehicle capability from the service built around it.\n\nASK THESE QUESTIONS IN ORDER:\n1. WHAT VEHICLE OR SYSTEM? Name the specific vehicle, platform and relevant hardware or software system.\n2. WHAT IS THE AUTONOMY STACK? Identify the disclosed sensor suite and architecture, including cameras, lidar, radar, perception software, planning system or named autonomy platform. Do not infer a design without evidence.\n3. WHAT IS THE OPERATIONAL DOMAIN? Specify where it operates: geofenced streets, an open urban network, a highway, a test track or another defined setting. Include relevant constraints such as geography, speed, weather, road type, supervision or service hours when disclosed.\n4. WHAT IS THE SAFETY RECORD? Report published miles or kilometres, incident figures and disengagement rates with their distance or conditions when available. Do not compare different denominators as though they were equivalent. If the available evidence contains no relevant published safety data, say so plainly.\n5. WHAT IS THE DEPLOYMENT STATUS? Distinguish research vehicle, test fleet, supervised pilot, commercial fleet and operating service. State fleet size, location and service availability only when established. Do not treat a demonstration or limited pilot as broad deployment.\n6. WHAT ARE THE REGULATORY OR COMMERCIAL IMPLICATIONS? Name the specific regulation, permit, exemption, regulator, operating approval or documented business model. Explain the concrete consequence without inventing legal permission or commercial viability.\n\nHARD RULES:\n- Separate the vehicle from the service. A car that drives itself is not, by itself, a taxi service or a commercially available transport service.\n- Do not state that a system is fully autonomous as an established fact. If a source makes that claim, attribute it and clarify that SAE Level 5 is the highest automation level; do not imply Level 5 has been demonstrated unless evidence supports that.\n- Do not use self-driving and autonomous interchangeably when the source distinguishes them. Match the source's terminology and explain any stated automation level.\n- Attribute future plans. Write that the company says it plans to expand, rather than presenting a plan as an accomplished fact.\n- Never invent sensor configurations, safety statistics, disengagement rates, fleet numbers, operational-domain limits, regulatory approvals or service availability.\n- Distinguish a driverless vehicle test from a driverless passenger service, a permit from a general operating approval, and a pilot from sustained commercial operation.\n\nFORMAT AND LENGTH: Return one finished autonomous-vehicle bulletin of no more than 120 words, with a specific headline and direct factual prose. Prioritise the named vehicle, autonomy stack, operational domain, safety evidence, deployment status and concrete regulatory or commercial implications. Include only details supported by the evidence. Return only the bulletin, without commentary or source notes.",
    },

    "sofia_lindqvist": {
        "name": "Sofia Lindqvist",
        "role": "Industrial Systems & Infrastructure Correspondent",
        "format": "industrial_bulletin",
        "instruction": "You are Sofia Lindqvist, Machina Daily's industrial systems and infrastructure correspondent. Determine whether an announcement is likely to become real production or remain a plan, pilot or demonstration. Your reader is an operations or supply-chain professional who cares about throughput, yield and physical constraints. Name the facility, process, capacity and bottleneck. Never let a phrase such as 'AI-powered manufacturing' substitute for a specific process description.\n\nASK THESE QUESTIONS IN ORDER:\n1. WHAT FACILITY OR SYSTEM? Name the specific fab, factory, plant, production line or infrastructure system. Include its location only as useful context, not as the finding.\n2. WHAT CHANGED? Identify the specific process, technology node, production line, equipment installation or capacity change. Explain the actual process rather than using broad labels.\n3. WHAT IS THE PRODUCTION CAPACITY? Report a quantified output per timeframe when the evidence provides it: units per day, wafers per month, tonnes per year or another relevant measure. Distinguish installed capacity, planned capacity, demonstrated output and actual production. If no number is established, state that capacity was not specified.\n4. WHAT IS THE PHYSICAL CONSTRAINT? Identify the documented limiting factor, such as energy, water, land, equipment, labour, materials, yield, logistics or commissioning. Explain how it constrains the project only when the evidence supports that link.\n5. WHAT IS THE SUPPLY-CHAIN IMPLICATION? Identify who receives the output, who supplies a critical input, and which customer, supplier or production dependency changes. Do not invent customers or imply that planned output has already been delivered.\n\nHARD RULES:\n- Never use 'smart factory' or 'Industry 4.0' without explaining the specific process or system involved.\n- Never write 'the company leverages AI to optimise' without naming what the AI actually optimises, such as inspection, scheduling, process control, maintenance or yield, and what evidence supports the claim.\n- Never call something 'scalable' without a supported quantitative measure. Give output per timeframe when established; otherwise say that scale has not been demonstrated or specified.\n- Keep pilot, test, demonstration, installation, commissioning and sustained production distinct.\n- A facility's location is context, not a finding. Lead with the process change or production consequence.\n- Do not invent capacity, yield, throughput, utilisation, cost reductions, bottlenecks, customer relationships, commissioning dates or supply-chain effects.\n- Do not treat planned capacity as current output, installed equipment as proven yield, or a successful pilot as sustained production.\n- If a key capacity or constraint figure is missing, state that limitation directly rather than filling it with promotional language.\n\nFORMAT AND LENGTH: Return one finished industrial systems and infrastructure bulletin of no more than 120 words, with a specific headline and direct factual prose. Prioritise the named facility, process change, quantified capacity where available, physical constraint and supply-chain implication. Include only details supported by the evidence. Return only the bulletin, without commentary or source notes.",
    },

}


# ======================================================================
# POST-PRODUCTION
# ======================================================================

MAREN = {
    "name": "Maren",
    "role": "Verification",
}

YUKI = {
    "name": "Yuki Tanaka",
    "role": "Desk Editor",
}

DANA = {
    "name": "Dana Okafor",
    "role": "Distribution / Push",
}


# ======================================================================
# GENERAL HELPERS
# ======================================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def normalise_text(value):
    if value is None:
        return ""

    if isinstance(value, list):
        return " ".join(normalise_text(x) for x in value)

    if isinstance(value, dict):
        return " ".join(
            f"{normalise_text(k)} {normalise_text(v)}"
            for k, v in value.items()
        )

    return str(value).strip()


def clean_title(value, limit=220):
    text = normalise_text(value)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def parse_date(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def safe_json_load(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )


def record_text(record):
    fields = [
        record.get("title"),
        record.get("source"),
        record.get("source_type"),
        record.get("development_type"),
        record.get("intelligence_state"),
        record.get("claims"),
        record.get("evidence"),
        record.get("open_questions"),
        record.get("entities"),
        record.get("specialist_routing"),
    ]

    return normalise_text(fields).lower()


def get_entities(record):
    entities = record.get("entities", [])

    if isinstance(entities, dict):
        return [
            normalise_text(k)
            for k in entities.keys()
        ]

    if isinstance(entities, list):
        output = []

        for item in entities:
            if isinstance(item, dict):
                for key in (
                    "name",
                    "entity",
                    "company",
                    "organisation",
                    "organization",
                    "title",
                ):
                    if item.get(key):
                        output.append(normalise_text(item[key]))
                        break
            else:
                output.append(normalise_text(item))

        return [x for x in output if x]

    return []


def compact_record(record):
    return {
        "record_id": record.get("record_id"),
        "title": record.get("title"),
        "source": record.get("source"),
        "url": record.get("url"),
        "date": record.get("date"),
        "source_type": record.get("source_type"),
        "development_type": record.get("development_type"),
        "entities": record.get("entities", []),
        "specialist_routing": record.get("specialist_routing", []),
        "claims": record.get("claims", []),
        "quantitative_signals": record.get(
            "quantitative_signals",
            [],
        ),
        "evidence": record.get("evidence", []),
        "intelligence_state": record.get(
            "intelligence_state",
            "",
        ),
        "open_questions": record.get(
            "open_questions",
            [],
        ),
        "evidence_available": record.get(
            "evidence_available",
            False,
        ),
        "facts_from_source": record.get(
            "facts_from_source",
            False,
        ),
        "independent_verification_performed": record.get(
            "independent_verification_performed",
            False,
        ),
    }


# ======================================================================
# INTELLIGENCE
# ======================================================================

def load_intelligence():
    data = safe_json_load(INTELLIGENCE_FILE, [])

    if isinstance(data, dict):
        for key in (
            "records",
            "briefs",
            "items",
            "intelligence",
        ):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        return []

    records = [
        x for x in data
        if isinstance(x, dict)
    ]

    records.sort(
        key=lambda x: parse_date(x.get("date")),
        reverse=True,
    )

    return records


# ======================================================================
# HISTORICAL COVERAGE
# ======================================================================

def history_files():
    if not HISTORY_DIR.exists():
        return []

    return sorted(
        HISTORY_DIR.glob("*/*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def load_previous_coverage():
    coverage = []

    for path in history_files():
        data = safe_json_load(path)

        if not isinstance(data, dict):
            continue

        journalist_id = data.get("journalist_id")

        if journalist_id not in WRITER_IDS:
            continue

        selected = data.get("selected_records", [])

        article = data.get("article", {})

        if not isinstance(selected, list):
            selected = []

        coverage.append(
            {
                "path": str(path),
                "journalist_id": journalist_id,
                "generated_at": data.get(
                    "generated_at"
                ),
                "selected_records": selected,
                "article": article,
            }
        )

    return coverage


def previous_subjects(coverage):
    subjects = {}

    for item in coverage:
        for record in item.get(
            "selected_records",
            [],
        ):
            entities = get_entities(record)

            for entity in entities:
                key = normalise_text(entity).lower()

                if not key:
                    continue

                subjects.setdefault(
                    key,
                    [],
                ).append(
                    {
                        "date": record.get("date"),
                        "title": record.get("title"),
                        "journalist_id": item.get(
                            "journalist_id"
                        ),
                        "path": item.get("path"),
                    }
                )

            title = clean_title(
                record.get("title")
            )

            if title:
                subjects.setdefault(
                    title.lower(),
                    [],
                ).append(
                    {
                        "date": record.get("date"),
                        "title": title,
                        "journalist_id": item.get(
                            "journalist_id"
                        ),
                        "path": item.get("path"),
                    }
                )

    return subjects


def record_subject_keys(record):
    keys = []

    for entity in get_entities(record):
        entity = normalise_text(entity).lower()

        if entity:
            keys.append(entity)

    title = clean_title(
        record.get("title")
    ).lower()

    if title:
        keys.append(title)

        words = re.findall(
            r"[a-z0-9]{4,}",
            title,
        )

        keys.extend(words)

    return set(keys)


def find_previous_subject(record, coverage):
    current_keys = record_subject_keys(record)

    if not current_keys:
        return None

    best = None
    best_score = 0

    for item in coverage:
        for previous in item.get(
            "selected_records",
            [],
        ):
            previous_keys = record_subject_keys(
                previous
            )

            overlap = current_keys & previous_keys

            if not overlap:
                continue

            score = len(overlap)

            if score > best_score:
                best_score = score
                best = {
                    "history": item,
                    "record": previous,
                    "overlap": sorted(overlap),
                }

    return best


# ======================================================================
# ROUTING
# ======================================================================

RESEARCH_SOURCE_TYPES = {
    "research",
    "academic",
    "paper",
    "preprint",
}

POLICY_SOURCE_TYPES = {
    "government",
    "regulation",
    "regulatory",
    "legislation",
    "policy",
}

PRODUCT_SOURCE_TYPES = {
    "product",
    "product_release",
    "launch",
}

MARKET_SOURCE_TYPES = {
    "business",
    "finance",
    "financial",
    "market",
    "company",
}

EVENT_SOURCE_TYPES = {
    "news",
    "incident",
    "court",
    "legal",
    "event",
}

RESEARCH_DEVELOPMENTS = {
    "research",
    "paper",
    "study",
    "benchmark",
    "experiment",
    "technical_research",
    "academic",
}

POLICY_DEVELOPMENTS = {
    "regulation",
    "regulatory",
    "policy",
    "legislation",
    "compliance",
    "government",
    "law",
    "directive",
}

PRODUCT_DEVELOPMENTS = {
    "launch",
    "release",
    "product",
    "feature",
    "api",
    "rollout",
    "availability",
    "version",
}

MARKET_DEVELOPMENTS = {
    "funding",
    "earnings",
    "revenue",
    "profit",
    "investment",
    "valuation",
    "acquisition",
    "ipo",
    "market",
    "price",
    "financial",
    "partnership",
    "deal",
}

EVENT_DEVELOPMENTS = {
    "incident",
    "court",
    "ruling",
    "hearing",
    "audit",
    "investigation",
    "arrest",
    "lawsuit",
    "trial",
    "accident",
    "event",
}


def title_matches(title, patterns):
    """
    Return True when the title contains a specific editorial signal.
    Generic words such as research, platform, system, technology and tool
    are deliberately excluded.
    """
    title = normalise_text(title).lower()

    for pattern in patterns:
        if re.search(pattern, title):
            return True

    return False


# ----------------------------------------------------------------------
# STRONG STORY-TYPE SIGNALS
# ----------------------------------------------------------------------

CALLUM_TITLE_SIGNALS = [
    r"\bcourt\b",
    r"\bruling\b",
    r"\bverdict\b",
    r"\bhearing\b",
    r"\blawsuit\b",
    r"\btrial\b",
    r"\barrest\b",
    r"\baccident\b",
    r"\bincident\b",
    r"\baudit\b",
    r"\binvestigation\b",
    r"\binvestigates\b",
    r"\binvestigated\b",
    r"\bcharged\b",
    r"\bindicted\b",
    r"\bsued\b",
]

INGRID_TITLE_SIGNALS = [
    r"\bregulation\b",
    r"\bregulatory\b",
    r"\blegislation\b",
    r"\bdirective\b",
    r"\bpolicy\b",
    r"\bgovernment policy\b",
    r"\bminister\b",
    r"\bparliament\b",
    r"\bcompliance requirement\b",
    r"\bnew rule\b",
    r"\bfinal rule\b",
    r"\bproposed rule\b",
]

DEV_TITLE_SIGNALS = [
    r"\blaunched\b",
    r"\blaunches\b",
    r"\blaunch\b",
    r"\breleased\b",
    r"\brelease\b",
    r"\brolls out\b",
    r"\brollout\b",
    r"\bnow available\b",
    r"\bnew feature\b",
    r"\bnew api\b",
    r"\bapi release\b",
    r"\bintroduces\b",
    r"\bintroduced\b",
    r"\bships\b",
    r"\bshipped\b",
    r"\bpublic preview\b",
    r"\bbeta release\b",
]

TOMAS_TITLE_SIGNALS = [
    r"\bearnings\b",
    r"\brevenue\b",
    r"\bprofit\b",
    r"\bloss\b",
    r"\bfunding\b",
    r"\braises\b",
    r"\braised\b",
    r"\binvestment\b",
    r"\bvaluation\b",
    r"\bacquisition\b",
    r"\bacquires\b",
    r"\bacquired\b",
    r"\bipo\b",
    r"\bshare price\b",
    r"\bstock price\b",
    r"\bmarket cap\b",
    r"\barr\b",
    r"\brevenue growth\b",
    r"\bfinancial results\b",
]

RAVI_TITLE_SIGNALS = [
    r"\bpaper\b",
    r"\bbenchmark\b",
    r"\bmethod\b",
    r"\bmethodology\b",
    r"\bneural\b",
    r"\btransformer\b",
    r"\bdiffusion\b",
    r"\bdecoder\b",
    r"\bencoder\b",
    r"\bmultimodal\b",
    r"\bimplicit surfaces\b",
    r"\barchitecture\b",
    r"\balgorithm\b",
    r"\btraining\b",
    r"\binference\b",
]

# Source types are supporting signals, NOT automatic routing rules.
RESEARCH_SOURCE_TYPES = {
    "research",
    "academic",
    "paper",
}

POLICY_SOURCE_TYPES = {
    "government",
    "regulator",
}

MARKET_SOURCE_TYPES = {
    "market",
    "company",
    "business",
    "finance",
}

EVENT_SOURCE_TYPES = {
    "event",
    "incident",
    "court",
    "legal",
}



def _record_text(record):
    parts = [
        str(record.get("title") or ""),
        str(record.get("source") or ""),
        str(record.get("development_type") or ""),
        str(record.get("source_type") or ""),
    ]

    claims = record.get("claims") or []
    if isinstance(claims, list):
        parts.extend(str(x) for x in claims)

    evidence = record.get("evidence") or []
    if isinstance(evidence, list):
        parts.extend(str(x) for x in evidence)

    return " ".join(parts).strip()


def _is_research_record(record):
    source_type = str(
        record.get("source_type") or ""
    ).lower()

    title = str(
        record.get("title") or ""
    ).lower()

    return (
        source_type == "research"
        or bool(
            re.search(
                r"\b(arxiv|paper|preprint|benchmark|"
                r"dataset|method|framework|architecture|"
                r"distillation|segmentation|representation|"
                r"transformer|lora|fMRI|"
                r"world model)\b",
                title,
                re.I,
            )
        )
    )


def _is_podcast(record):
    return str(
        record.get("source_type") or ""
    ).lower() == "podcast"


def _date_value(record):
    raw = str(
        record.get("date") or ""
    ).strip()

    if not raw:
        return None

    try:
        from datetime import datetime
        return datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        )
    except Exception:
        return None


def _recency_bonus(record):
    dt = _date_value(record)

    if dt is None:
        return 0

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    age_days = max(
        0,
        (now - dt).days,
    )

    if age_days <= 7:
        return 12

    if age_days <= 30:
        return 9

    if age_days <= 90:
        return 6

    if age_days <= 180:
        return 3

    if age_days <= 365:
        return 1

    return 0



def _newsworthiness_bonus(record):
    """Return a modest 0-6 point bonus from the newsworthiness engine."""
    try:
        score = float(record.get("newsworthiness_score", 0))
    except (TypeError, ValueError):
        return 0

    score = max(12.0, min(42.0, score))
    return round((score - 12.0) / 30.0 * 6.0, 2)


def _has_any(text, patterns):
    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern in patterns
    )


def _specialist_score(record, desk):
    routing = record.get(
        "specialist_routing"
    )

    if not isinstance(routing, dict):
        return 0

    item = routing.get(
        desk.upper()
    )

    if isinstance(item, dict):
        value = item.get("score")
        try:
            return int(value or 0)
        except Exception:
            return 0

    try:
        return int(item or 0)
    except Exception:
        return 0


EVENT_PATTERNS = [
    r"\bdepart(?:s|ed)?\b",
    r"\barrest(?:s|ed)?\b",
    r"\bcharg(?:e|ed|es)\b",
    r"\brul(?:e|ed|ing)\b",
    r"\bconvict(?:ed|ion)\b",
    r"\bsentenc(?:ed|ing)\b",
    r"\binjur(?:ed|y|ies)\b",
    r"\bkilled\b",
    r"\bdied\b",
    r"\bdrop(?:s|ped)?\b",
    r"\bfailed\b",
    r"\bblock(?:ed|s)?\b",
    r"\bapprov(?:ed|es|al)\b",
    r"\breject(?:ed|s|ion)\b",
    r"\border(?:ed|s)?\b",
    r"\bbann?ed\b",
    r"\bseiz(?:ed|ure)\b",
    r"\braid(?:ed|s)?\b",
    r"\bincident\b",
    r"\baccident\b",
    r"\bcrash(?:ed|es)?\b",
    r"\bfire\b",
    r"\battack(?:ed|s)?\b",
    r"\bbreach(?:ed|es)?\b",
    r"\boutage\b",
    r"\bexercise\b",
    r"\btrial(?:s)?\b",
    r"\bdemonstrat(?:es|ed|ion)\b",
    r"\bcreates?\b",
    r"\bestablish(?:es|ed|ment)\b",
]

BUSINESS_PATTERNS = [
    r"\brais(?:e|ed|es|ing)\b",
    r"\bfund(?:ed|ing|s)?\b",
    r"\binvest(?:s|ed|ment|ing)?\b",
    r"\brevenue\b",
    r"\barr\b",
    r"\bearnings?\b",
    r"\bprofit\b",
    r"\bloss\b",
    r"\bvaluation\b",
    r"\bvalued\b",
    r"\bacquir(?:e|ed|es|ing)\b",
    r"\bmerger\b",
    r"\bmerg(?:e|es|ed)\b",
    r"\bpartnership\b",
    r"\bpartner(?:s|ed|ing)?\b",
    r"\bcontract(?:s|ed)?\b",
    r"\bdeal\b",
    r"\bagreement\b",
    r"\bsales?\b",
    r"\bpricing\b",
    r"\bprice\b",
    r"\bproduction\b",
    r"\bexpan(?:d|ded|s|sion)\b",
    r"\baward(?:ed|s)?\b",
    r"\bmilestone(?:s)?\b",
]

POLICY_PATTERNS = [
    r"\bregulation(?:s)?\b",
    r"\bregulatory\b",
    r"\blegislation\b",
    r"\blegislative\b",
    r"\blaw(?:s)?\b",
    r"\bbill\b",
    r"\bact\b",
    r"\brule(?:s)?\b",
    r"\bguidance\b",
    r"\bconsultation\b",
    r"\bconsult(?:s|ed|ation)?\b",
    r"\bproposal\b",
    r"\bpropos(?:e|es|ed|ing)\b",
    r"\brequire(?:s|d|ment|ments)?\b",
    r"\bban(?:s|ned)?\b",
    r"\bprohibit(?:s|ed|ion)\b",
    r"\bmandat(?:e|ed|es|ory)\b",
    r"\blicen[cs](?:e|ed|ing|es)\b",
    r"\blicensing\b",
    r"\bframework\b",
    r"\bstandards?\b",
    r"\bdeadline\b",
]

POLICY_ACTION_PATTERNS = [
    r"\bissued\b",
    r"\bpublishes?\b",
    r"\bpublished\b",
    r"\bintroduces?\b",
    r"\bintroduced\b",
    r"\bannounces?\b",
    r"\bannounced\b",
    r"\bproposes?\b",
    r"\bproposed\b",
    r"\bconsultation\b",
    r"\bopens?\b",
    r"\brequires?\b",
    r"\brequires?\b",
    r"\bapproved\b",
    r"\bpassed\b",
    r"\bcomes into force\b",
    r"\beffective\b",
    r"\bdeadline\b",
]

PRODUCT_ACTION_PATTERNS = [
    r"\bintroduces?\b",
    r"\bintroduced\b",
    r"\blaunch(?:es|ed)?\b",
    r"\brelease(?:s|d)?\b",
    r"\bunveil(?:s|ed)?\b",
    r"\bdebut(?:s|ed)?\b",
    r"\bship(?:s|ped|ping)?\b",
    r"\bavailable\b",
    r"\bavailability\b",
    r"\bgeneral availability\b",
    r"\bnow available\b",
    r"\bnew feature\b",
    r"\bnew features\b",
    r"\badds?\b",
    r"\badded\b",
    r"\brolls out\b",
    r"\brolled out\b",
]

PRODUCT_NOUN_PATTERNS = [
    r"\bproduct\b",
    r"\bplatform\b",
    r"\btool\b",
    r"\bsoftware\b",
    r"\bapi\b",
    r"\bmodel\b",
    r"\bdevice\b",
    r"\bsystem\b",
    r"\bservice\b",
    r"\bapplication\b",
    r"\bapp\b",
    r"\bhardware\b",
    r"\bfeature\b",
    r"\bgateway\b",
    r"\brobot\b",
    r"\bdrone\b",
    r"\bvehicle\b",
    r"\baircraft\b",
]

RESEARCH_PATTERNS = [
    r"\bresearch\b",
    r"\bstudy\b",
    r"\bpaper\b",
    r"\bpreprint\b",
    r"\bbenchmark\b",
    r"\bmethod\b",
    r"\bframework\b",
    r"\barchitecture\b",
    r"\balgorithm\b",
    r"\bdataset\b",
    r"\bdistillation\b",
    r"\bsegmentation\b",
    r"\brepresentation\b",
    r"\btraining\b",
    r"\bmodel\b",
]

GOVERNMENT_SOURCE_PATTERNS = [
    r"\bgovernment\b",
    r"\bministry\b",
    r"\bdepartment\b",
    r"\bregulator\b",
    r"\bregulatory\b",
    r"\bcommission\b",
    r"\bauthority\b",
    r"\bofficial statistics\b",
]


def story_type_score(record, writer_id):
    text = _record_text(record)
    title = str(
        record.get("title") or ""
    )
    source = str(
        record.get("source") or ""
    )

    lower = text.lower()

    score = 0
    reasons = []

    research = _is_research_record(record)
    podcast = _is_podcast(record)

    if writer_id == "elena_vasquez":
        drone_patterns = [
            r"\bdrone\b",
            r"\bdrones\b",
            r"\buav\b",
            r"\buas\b",
            r"\buncrewed aircraft\b",
            r"\buncrewed aerial\b",
            r"\bcounter[- ]uas\b",
            r"\bcounter[- ]drone\b",
            r"\bdrone system\b",
            r"\bdrone systems\b",
            r"\bdrone swarm\b",
            r"\bloitering munition\b",
            r"\baerial autonomy\b",
            r"\bautonomous aircraft\b",
            r"\bflight autonomy\b",
            r"\bdrone manufacturing\b",
        ]

        if _has_any(title, drone_patterns):
            score += 12
            reasons.append("drone/uncrewed title signal")

        if _has_any(lower, drone_patterns):
            score += 5
            reasons.append("drone/uncrewed body signal")

        if _has_any(
            title,
            [
                r"launch(?:es|ed)?",
                r"debut(?:s|ed)?",
                r"deploy(?:s|ed|ment)?",
                r"test(?:s|ed|ing)?",
                r"demonstrat(?:es|ed|ion)",
                r"contract",
                r"production",
                r"manufactur",
                r"integrat",
                r"showcase",
            ],
        ):
            score += 4
            reasons.append("drone development action")

        score += _specialist_score(record, "ALPHA")

        return score, reasons

    if writer_id == "marcus_okafor":
        robotics_patterns = [
            r"\brobot\b",
            r"\brobots\b",
            r"\brobotics\b",
            r"\brobotic\b",
            r"\bhumanoid\b",
            r"\bhumanoids\b",
            r"\bindustrial robot\b",
            r"\bwarehouse robot\b",
            r"\brobot arm\b",
            r"\bmanipulation\b",
            r"\bembodied ai\b",
            r"\bembodied intelligence\b",
            r"\brobot learning\b",
            r"\brobot hardware\b",
        ]

        if _has_any(title, robotics_patterns):
            score += 12
            reasons.append("robotics title signal")

        if _has_any(lower, robotics_patterns):
            score += 5
            reasons.append("robotics body signal")

        if _has_any(
            title,
            [
                r"launch(?:es|ed)?",
                r"debut(?:s|ed)?",
                r"deploy(?:s|ed|ment)?",
                r"test(?:s|ed|ing)?",
                r"demonstrat(?:es|ed|ion)",
                r"introduc(?:es|ed|tion)",
                r"production",
                r"manufactur",
                r"pilot",
            ],
        ):
            score += 4
            reasons.append("robotics development action")

        score += _specialist_score(record, "ALPHA")

        return score, reasons

    if writer_id == "kenji_nakamura":
        av_patterns = [
            r"\bautonomous vehicle\b",
            r"\bautonomous vehicles\b",
            r"\bself[- ]driving\b",
            r"\bself driving\b",
            r"\bdriverless\b",
            r"\brobotaxi\b",
            r"\brobotaxis\b",
            r"\bautonomous truck\b",
            r"\bautonomous trucks\b",
            r"\bautonomous delivery\b",
            r"\bvehicle autonomy\b",
            r"\bautonomy stack\b",
            r"\bdriving stack\b",
            r"\bautonomous driving\b",
            r"\bautomated driving\b",
        ]

        if _has_any(title, av_patterns):
            score += 12
            reasons.append("autonomous-vehicle title signal")

        if _has_any(lower, av_patterns):
            score += 5
            reasons.append("autonomous-vehicle body signal")

        if _has_any(
            title,
            [
                r"launch(?:es|ed)?",
                r"deploy(?:s|ed|ment)?",
                r"test(?:s|ed|ing)?",
                r"pilot",
                r"approved",
                r"approval",
                r"commercial",
                r"service",
                r"expands?",
                r"introduc(?:es|ed|tion)",
            ],
        ):
            score += 4
            reasons.append("autonomous-vehicle development action")

        score += _specialist_score(record, "ALPHA")

        return score, reasons

    if writer_id == "sofia_lindqvist":
        industrial_patterns = [
            r"\bsemiconductor fab\b",
            r"\bfab\b",
            r"\bfabrication plant\b",
            r"\bchip plant\b",
            r"\bmanufactur(?:e|ing|er)\b",
            r"\bfactor(?:y|ies)\b",
            r"\bindustrial automation\b",
            r"\bdata cent(?:er|re)s?\b",
            r"\bdata centre\b",
            r"\bdata center\b",
            r"\benergy infrastructure\b",
            r"\bpower infrastructure\b",
            r"\bsupply chain\b",
            r"\bproduction capacity\b",
            r"\bproduction facility\b",
            r"\bindustrial facility\b",
            r"\binfrastructure project\b",
        ]

        if _has_any(title, industrial_patterns):
            score += 12
            reasons.append("industrial/infrastructure title signal")

        if _has_any(lower, industrial_patterns):
            score += 5
            reasons.append("industrial/infrastructure body signal")

        if _has_any(
            title,
            [
                r"build(?:s|ing)?",
                r"construct(?:s|ed|ion)?",
                r"expand(?:s|ed|ing|sion)?",
                r"open(?:s|ed|ing)?",
                r"launch(?:es|ed)?",
                r"production",
                r"manufactur",
                r"invest(?:s|ed|ment)?",
                r"facility",
            ],
        ):
            score += 4
            reasons.append("industrial development action")

        score += _specialist_score(record, "BETA")

        return score, reasons

    if writer_id == "ravi_chatterjee":
        if research:
            score += 10
            reasons.append("research record")

        if any(
            re.search(pattern, lower)
            for pattern in RESEARCH_PATTERNS
        ):
            score += 8
            reasons.append("technical research language")

        return score, reasons

    if writer_id == "callum_reyes":
        # Podcasts can contain descriptions of events, but the
        # podcast publication date is not necessarily the event
        # date. Do not turn podcast discussion into a current event.
        if podcast:
            return 0, [
                "podcast source excluded from event desk"
            ]

        # Administrative/research approval is not itself a
        # real-world event for Callum.
        if _has_any(
            title,
            [
                r"applying for approval",
                r"application for approval",
                r"published research",
                r"research involving humans",
            ],
        ):
            return 0, [
                "administrative/research record"
            ]

        if _has_any(
            title,
            EVENT_PATTERNS,
        ):
            score += 8
            reasons.append(
                "dated event title signal"
            )

        if _has_any(
            lower,
            EVENT_PATTERNS,
        ):
            score += 3
            reasons.append(
                "event language"
            )

        if _has_any(
            source,
            GOVERNMENT_SOURCE_PATTERNS,
        ):
            score += 2
            reasons.append(
                "official/event source"
            )

        score += _specialist_score(
            record,
            "GAMMA",
        )

        return score, reasons

    if writer_id == "elena_vasquez":
        if podcast:
            title_hits = _has_any(
                title,
                [
                    r"drone",
                    r"drones",
                    r"uav",
                    r"uas",
                    r"uncrewed",
                    r"counter[- ]drone",
                    r"counter[- ]uas",
                ],
            )

            if not title_hits:
                return 0, [
                    "podcast lacks explicit drone intelligence"
                ]

        hits = _has_any(
            title_lower,
            [
                r"drone",
                r"drones",
                r"uav",
                r"uas",
                r"uncrewed",
                r"counter[- ]uas",
                r"counter[- ]drone",
                r"loitering",
                r"autonomous aircraft",
            ],
        )

        if hits:
            score += 9
            reasons.append("drone fallback signal")

        if _has_any(
            lower,
            [
                r"drone system",
                r"drone systems",
                r"uncrewed aircraft",
                r"counter[- ]uas",
                r"flight autonomy",
                r"drone manufacturing",
            ],
        ):
            score += 4
            reasons.append("drone technical evidence")

        return (
            (score, reasons)
            if score >= 8
            else (0, ["insufficient drone fallback signal"])
        )

    if writer_id == "marcus_okafor":
        if podcast:
            title_hits = _has_any(
                title,
                [
                    r"robot",
                    r"robotics",
                    r"humanoid",
                    r"embodied",
                ],
            )

            if not title_hits:
                return 0, [
                    "podcast lacks explicit robotics intelligence"
                ]

        if _has_any(
            title_lower,
            [
                r"robot",
                r"robotics",
                r"humanoid",
                r"industrial robot",
                r"warehouse robot",
                r"embodied ai",
                r"robot learning",
            ],
        ):
            score += 9
            reasons.append("robotics fallback signal")

        if _has_any(
            lower,
            [
                r"robotic hardware",
                r"robot arm",
                r"manipulation",
                r"robot learning",
                r"embodied intelligence",
            ],
        ):
            score += 4
            reasons.append("robotics technical evidence")

        return (
            (score, reasons)
            if score >= 8
            else (0, ["insufficient robotics fallback signal"])
        )

    if writer_id == "kenji_nakamura":
        if podcast:
            title_hits = _has_any(
                title,
                [
                    r"autonomous vehicle",
                    r"self[- ]driving",
                    r"driverless",
                    r"robotaxi",
                    r"autonomous truck",
                ],
            )

            if not title_hits:
                return 0, [
                    "podcast lacks explicit autonomous-vehicle intelligence"
                ]

        if _has_any(
            title_lower,
            [
                r"autonomous vehicle",
                r"self[- ]driving",
                r"driverless",
                r"robotaxi",
                r"autonomous truck",
                r"autonomous delivery",
                r"vehicle autonomy",
            ],
        ):
            score += 9
            reasons.append("autonomous-vehicle fallback signal")

        if _has_any(
            lower,
            [
                r"autonomy stack",
                r"driving stack",
                r"vehicle autonomy",
                r"autonomous driving",
                r"automated driving",
            ],
        ):
            score += 4
            reasons.append("autonomous-vehicle technical evidence")

        return (
            (score, reasons)
            if score >= 8
            else (0, ["insufficient autonomous-vehicle fallback signal"])
        )

    if writer_id == "sofia_lindqvist":
        if _has_any(
            title_lower,
            [
                r"semiconductor fab",
                r"fabrication plant",
                r"chip plant",
                r"manufacturing",
                r"factory",
                r"factories",
                r"industrial automation",
                r"data centre",
                r"data center",
                r"energy infrastructure",
                r"power infrastructure",
                r"supply chain",
                r"production capacity",
                r"production facility",
                r"infrastructure project",
            ],
        ):
            score += 9
            reasons.append("industrial/infrastructure fallback signal")

        if _has_any(
            lower,
            [
                r"manufacturing facility",
                r"production facility",
                r"semiconductor fabrication",
                r"factory",
                r"data centre",
                r"data center",
                r"supply chain",
                r"production capacity",
            ],
        ):
            score += 4
            reasons.append("industrial evidence")

        return (
            (score, reasons)
            if score >= 8
            else (0, ["insufficient industrial fallback signal"])
        )

    if writer_id == "tomas_vega":
        # Official government statistics are not automatically
        # business stories. A statistics publication can contain
        # words such as "trade", "industry" or "contracts" while
        # still being a statistical release rather than a company,
        # market, funding, earnings or deal story.
        if (
            str(record.get("source_type") or "").lower()
            == "government"
            and _has_any(
                title,
                [
                    r"official statistics",
                    r"accredited official statistics",
                    r"national statistics",
                    r"statistical release",
                    r"statistics:",
                    r"statistics$",
                ],
            )
        ):
            return 0, [
                "government statistics excluded from business desk"
            ]

        if _has_any(
            title,
            BUSINESS_PATTERNS,
        ):
            score += 8
            reasons.append(
                "business title signal"
            )

        if _has_any(
            lower,
            BUSINESS_PATTERNS,
        ):
            score += 3
            reasons.append(
                "business development"
            )

        if record.get(
            "quantitative_signals"
        ):
            score += 1
            reasons.append(
                "quantitative business signal"
            )

        score += _specialist_score(
            record,
            "BETA",
        )

        return score, reasons

    if writer_id == "ingrid_sorensen":
        government_source = _has_any(
            source,
            GOVERNMENT_SOURCE_PATTERNS,
        ) or str(
            record.get("source_type") or ""
        ).lower() == "government"

        policy_title = _has_any(
            title,
            POLICY_PATTERNS,
        )

        policy_action = _has_any(
            lower,
            POLICY_ACTION_PATTERNS,
        )

        # Generic Guidance pages are usually operational/public
        # information rather than a policy or regulatory change.
        # Ingrid should only receive guidance when the title itself
        # contains a genuine policy/regulatory action.
        if re.match(r"^guidance:\s*", title, re.I):
            genuine_guidance_policy = _has_any(
                title,
                [
                    r"regulation",
                    r"regulatory",
                    r"legislation",
                    r"legislative",
                    r"policy",
                    r"requirement",
                    r"requirements",
                    r"rules?",
                    r"law",
                    r"legal",
                    r"compliance",
                    r"consultation",
                    r"propos(?:al|es?)",
                    r"amend(?:ed|ment|s)?",
                    r"ban(?:ned|ning)?",
                    r"licen[cs](?:e|ing|ed)",
                    r"tax",
                    r"duty",
                    r"sanction",
                    r"restriction",
                    r"restrictions",
                ],
            )
            if not genuine_guidance_policy:
                return 0, [
                    "generic guidance excluded"
                ]

        # Research is Ravi's territory. Government research pages
        # are not automatically policy.
        if research:
            return 0, [
                "research excluded from policy desk"
            ]

        # A government source alone is insufficient.
        if not policy_title:
            return 0, [
                "no explicit policy title"
            ]

        if government_source:
            score += 4
            reasons.append(
                "government/regulator source"
            )

        score += 5
        reasons.append(
            "policy title signal"
        )

        if policy_action:
            score += 5
            reasons.append(
                "policy action"
            )

        # A title such as "guidance" or "regulation" is useful
        # even when the intelligence has not supplied a detailed
        # effective date yet.
        score += _specialist_score(
            record,
            "INGRID",
        )

        return score, reasons

    if writer_id == "dev_okafor":
        # Podcasts are discussion sources, not product release
        # records, even when the title contains "feature",
        # "product", "ship", etc.
        if podcast:
            return 0, [
                "podcast excluded from product desk"
            ]

        product_title = _has_any(
            title,
            PRODUCT_NOUN_PATTERNS
            + [
                r"browser",
                r"assistant",
                r"gateway",
            ],
        )

        product_action = _has_any(
            title,
            PRODUCT_ACTION_PATTERNS
            + [
                r"bringing",
                r"brings",
                r"now supports",
                r"supports",
                r"introducing",
            ],
        )

        if not product_action:
            return 0, [
                "no concrete release action"
            ]

        if not product_title:
            return 0, [
                "no concrete product noun"
            ]

        score += 7
        reasons.append(
            "product title signal"
        )

        score += 5
        reasons.append(
            "release action"
        )

        score += 3
        reasons.append(
            "product noun"
        )

        score += _specialist_score(
            record,
            "ALPHA",
        )

        return score, reasons

    return 0, ["no desk rule"]


def editorial_fallback_score(record, writer_id):
    """
    Second-stage editorial routing for records that do not satisfy
    the strict primary desk rules.

    This deliberately uses softer signals so the intelligence pool
    does not collapse simply because provenance/source_type is unusual.
    It still requires meaningful editorial evidence.
    """

    text = _record_text(record)
    title = str(
        record.get("title") or ""
    )
    source = str(
        record.get("source") or ""
    )

    lower = text.lower()
    title_lower = title.lower()

    podcast = _is_podcast(record)
    research = _is_research_record(record)

    score = 0
    reasons = []

    if writer_id == "ingrid_sorensen":
        government = (
            str(record.get("source_type") or "").lower()
            == "government"
            or _has_any(
                source,
                GOVERNMENT_SOURCE_PATTERNS,
            )
        )

        policy_signal = _has_any(
            title,
            POLICY_PATTERNS,
        )

        policy_action = _has_any(
            title_lower,
            POLICY_ACTION_PATTERNS,
        )

        government_topic = _has_any(
            lower,
            [
                r"government",
                r"ministry",
                r"department",
                r"regulator",
                r"regulatory",
                r"defence",
                r"defense",
                r"dstl",
                r"nato",
                r"darpa",
                r"sbir",
                r"procurement",
                r"national security",
            ],
        )

        if government:
            score += 5
            reasons.append(
                "government provenance"
            )

        if policy_signal:
            score += 5
            reasons.append(
                "policy language"
            )

        if policy_action:
            score += 4
            reasons.append(
                "policy action"
            )

        if government_topic:
            score += 3
            reasons.append(
                "government/strategic topic"
            )

        # Research remains Ravi's primary territory unless there is
        # an unmistakable policy/government action.
        if research and not (
            government
            and policy_signal
        ):
            return 0, [
                "research retained for technical desk"
            ]

        if score >= 8:
            return score, reasons

        return 0, [
            "insufficient policy fallback signal"
        ]

    if writer_id == "dev_okafor":
        # Podcasts remain excluded unless the title itself clearly
        # describes a product or software launch. This prevents generic
        # podcast discussion from becoming fake product journalism.
        if podcast:
            return 0, [
                "podcast excluded from product fallback"
            ]

        product_signal = _has_any(
            title,
            PRODUCT_NOUN_PATTERNS
            + [
                r"browser",
                r"assistant",
                r"gateway",
                r"cli",
                r"framework",
                r"library",
                r"robot",
                r"drone",
                r"vehicle",
            ],
        )

        action_signal = _has_any(
            title,
            PRODUCT_ACTION_PATTERNS
            + [
                r"introducing",
                r"introduces",
                r"brings",
                r"bringing",
                r"adds?",
                r"supports?",
                r"expands?",
                r"now offers",
                r"now supports",
            ],
        )

        technical_release = _has_any(
            lower,
            [
                r"general availability",
                r"now available",
                r"available today",
                r"new version",
                r"new release",
                r"release notes",
                r"launches",
                r"launched",
                r"introduced",
                r"ships",
                r"shipped",
            ],
        )

        if product_signal:
            score += 5
            reasons.append(
                "product/software signal"
            )

        if action_signal:
            score += 6
            reasons.append(
                "product action"
            )

        if technical_release:
            score += 3
            reasons.append(
                "release language"
            )

        if score >= 10:
            return score, reasons

        return 0, [
            "insufficient product fallback signal"
        ]

    if writer_id == "tomas_vega":
        business_signal = _has_any(
            title,
            BUSINESS_PATTERNS,
        )

        company_development = _has_any(
            lower,
            [
                r"company",
                r"startup",
                r"business",
                r"customer",
                r"customers",
                r"enterprise",
                r"commercial",
                r"market",
                r"industry",
                r"revenue",
                r"funding",
                r"investment",
                r"investor",
                r"acquisition",
                r"acquired",
                r"partnership",
                r"partner",
                r"contract",
                r"deal",
                r"expansion",
                r"expands",
                r"international",
            ],
        )

        quantitative = bool(
            record.get("quantitative_signals")
        )

        if business_signal:
            score += 6
            reasons.append(
                "business signal"
            )

        if company_development:
            score += 4
            reasons.append(
                "company/market development"
            )

        if quantitative:
            score += 2
            reasons.append(
                "quantitative signal"
            )

        # Podcasts can be useful here when they are actually about
        # companies, markets, funding or business strategy.
        if podcast and company_development:
            score += 2
            reasons.append(
                "business podcast intelligence"
            )

        if score >= 8:
            return score, reasons

        return 0, [
            "insufficient business fallback signal"
        ]

    if writer_id == "callum_reyes":
        # Do not manufacture current events from generic podcasts.
        if podcast:
            return 0, [
                "podcast excluded from event fallback"
            ]

        event_title = _has_any(
            title,
            EVENT_PATTERNS,
        )

        event_language = _has_any(
            lower,
            EVENT_PATTERNS,
        )

        current_action = _has_any(
            title_lower,
            [
                r"announces?",
                r"announced",
                r"reveals?",
                r"revealed",
                r"reports?",
                r"reported",
                r"opens?",
                r"closes?",
                r"departs?",
                r"arrives?",
                r"achieves?",
                r"achieved",
                r"wins?",
                r"won",
                r"fails?",
                r"failed",
            ],
        )

        if event_title:
            score += 7
            reasons.append(
                "event title signal"
            )

        if event_language:
            score += 3
            reasons.append(
                "event language"
            )

        if current_action:
            score += 4
            reasons.append(
                "current development"
            )

        if score >= 8:
            return score, reasons

        return 0, [
            "insufficient event fallback signal"
        ]

    if writer_id == "elena_vasquez":
        score = 0

        if _has_any(
            title_lower,
            [
                r"drone",
                r"drones",
                r"uav",
                r"uas",
                r"uncrewed",
                r"counter[- ]uas",
                r"counter[- ]drone",
                r"loitering",
                r"autonomous aircraft",
                r"flight autonomy",
            ],
        ):
            score += 10
            reasons.append("drone fallback signal")

        if _has_any(
            lower,
            [
                r"drone system",
                r"drone systems",
                r"uncrewed aircraft",
                r"counter[- ]uas",
                r"drone manufacturing",
                r"flight autonomy",
            ],
        ):
            score += 5
            reasons.append("drone technical evidence")

        if _has_any(
            title_lower,
            [
                r"launch",
                r"deploy",
                r"test",
                r"demonstrat",
                r"contract",
                r"production",
                r"manufactur",
                r"integrat",
            ],
        ):
            score += 3
            reasons.append("drone development action")

        return (
            (score, reasons)
            if score >= 8
            else (0, ["insufficient drone fallback signal"])
        )

    if writer_id == "marcus_okafor":
        score = 0

        if _has_any(
            title_lower,
            [
                r"robot",
                r"robots",
                r"robotics",
                r"humanoid",
                r"industrial robot",
                r"warehouse robot",
                r"embodied ai",
                r"robot learning",
            ],
        ):
            score += 10
            reasons.append("robotics fallback signal")

        if _has_any(
            lower,
            [
                r"robotic hardware",
                r"robot arm",
                r"manipulation",
                r"embodied intelligence",
                r"robot learning",
            ],
        ):
            score += 5
            reasons.append("robotics technical evidence")

        if _has_any(
            title_lower,
            [
                r"launch",
                r"deploy",
                r"test",
                r"demonstrat",
                r"introduc",
                r"production",
                r"manufactur",
                r"pilot",
            ],
        ):
            score += 3
            reasons.append("robotics development action")

        return (
            (score, reasons)
            if score >= 8
            else (0, ["insufficient robotics fallback signal"])
        )

    if writer_id == "kenji_nakamura":
        score = 0

        if _has_any(
            title_lower,
            [
                r"autonomous vehicle",
                r"autonomous vehicles",
                r"self[- ]driving",
                r"driverless",
                r"robotaxi",
                r"robotaxis",
                r"autonomous truck",
                r"autonomous trucks",
                r"autonomous delivery",
                r"vehicle autonomy",
                r"autonomous driving",
            ],
        ):
            score += 10
            reasons.append("autonomous-vehicle fallback signal")

        if _has_any(
            lower,
            [
                r"autonomy stack",
                r"driving stack",
                r"vehicle autonomy",
                r"autonomous driving",
                r"automated driving",
            ],
        ):
            score += 5
            reasons.append("autonomous-vehicle technical evidence")

        if _has_any(
            title_lower,
            [
                r"launch",
                r"deploy",
                r"test",
                r"pilot",
                r"approved",
                r"approval",
                r"commercial",
                r"service",
                r"expand",
                r"introduc",
            ],
        ):
            score += 3
            reasons.append("autonomous-vehicle development action")

        return (
            (score, reasons)
            if score >= 8
            else (0, ["insufficient autonomous-vehicle fallback signal"])
        )

    if writer_id == "sofia_lindqvist":
        score = 0

        if _has_any(
            title_lower,
            [
                r"semiconductor fab",
                r"fabrication plant",
                r"chip plant",
                r"manufacturing",
                r"factory",
                r"factories",
                r"industrial automation",
                r"data centre",
                r"data center",
                r"energy infrastructure",
                r"power infrastructure",
                r"supply chain",
                r"production capacity",
                r"production facility",
                r"infrastructure project",
            ],
        ):
            score += 10
            reasons.append("industrial/infrastructure fallback signal")

        if _has_any(
            lower,
            [
                r"manufacturing facility",
                r"production facility",
                r"semiconductor fabrication",
                r"factory",
                r"data centre",
                r"data center",
                r"supply chain",
                r"production capacity",
            ],
        ):
            score += 5
            reasons.append("industrial evidence")

        if _has_any(
            title_lower,
            [
                r"build",
                r"construct",
                r"expand",
                r"open",
                r"production",
                r"manufactur",
                r"invest",
                r"facility",
            ],
        ):
            score += 3
            reasons.append("industrial development action")

        return (
            (score, reasons)
            if score >= 8
            else (0, ["insufficient industrial fallback signal"])
        )

    if writer_id == "ravi_chatterjee":
        technical_signal = _has_any(
            title,
            RESEARCH_PATTERNS
            + [
                r"ai",
                r"llm",
                r"machine learning",
                r"deep learning",
                r"neural",
                r"inference",
                r"training",
                r"benchmark",
                r"evaluation",
                r"evaluating",
                r"rag",
                r"autonomy",
                r"robotics",
                r"computer vision",
                r"multimodal",
                r"model",
                r"algorithm",
                r"dataset",
                r"architecture",
                r"engineering",
                r"technical",
            ],
        )

        research_language = _has_any(
            lower,
            RESEARCH_PATTERNS,
        )

        if technical_signal:
            score += 7
            reasons.append(
                "technical title signal"
            )

        if research_language:
            score += 5
            reasons.append(
                "technical research language"
            )

        if research:
            score += 5
            reasons.append(
                "research provenance"
            )

        if score >= 8:
            return score, reasons

        return 0, [
            "insufficient technical fallback signal"
        ]

    return 0, ["no fallback desk rule"]



def intelligence_gate_score(record, writer_id):
    """
    Controlled second-chance routing for records that contain
    meaningful editorial intelligence but do not satisfy the
    stricter primary desk rules.

    Title signals are deliberately weighted heavily because many
    intelligence records have sparse or missing body text.
    """

    title = str(
        record.get("title")
        or ""
    ).strip()

    text_value = str(
        record.get("text")
        or record.get("content")
        or record.get("summary")
        or ""
    )

    source_type = str(
        record.get("source_type")
        or ""
    ).lower()

    lower_title = title.lower()
    lower_text = text_value.lower()
    combined = f"{lower_title} {lower_text}"

    # --------------------------------------------------------------
    # HARD EXCLUSIONS
    # --------------------------------------------------------------

    generic_exclusions = [
        "career growth",
        "career advice",
        "getting into management",
        "personal growth",
        "team building",
        "high-performing teams",
        "typography",
        "logos",
        "lettering",
        "how to see like a designer",
        "coffee",
        "restaurant",
        "sports",
        "football",
        "basketball",
        "baseball",
        "the la clippers",
        "grief",
        "loneliness",
        "burnout",
        "own your career",
        "rise within your company",
        "welcome to my new podcast",
        "ultimate guide to pr",
        "how to own your career",
        "how to be more innovative",
        "art of influence",
        "changing teams",
        "self-made engineer",
    ]

    if any(
        phrase in lower_title
        for phrase in generic_exclusions
    ):
        return 0

    # --------------------------------------------------------------
    # STRONG TITLE-LEVEL INTELLIGENCE
    # --------------------------------------------------------------

    technical_title_signals = [
        "ai",
        "artificial intelligence",
        "llm",
        "large language model",
        "machine learning",
        "deep learning",
        "neural",
        "inference",
        "training",
        "benchmark",
        "evaluation",
        "evaluating",
        "rag",
        "retrieval",
        "agentic",
        "agents",
        "robotics",
        "robot",
        "autonomy",
        "autonomous",
        "computer vision",
        "multimodal",
        "algorithm",
        "dataset",
        "architecture",
        "gpu",
        "chip",
        "semiconductor",
        "software",
        "api",
        "cli",
        "model",
        "models",
        "ocr",
        "hypersonic",
        "propulsion",
    ]

    business_title_signals = [
        "funding",
        "funded",
        "investment",
        "invested",
        "investor",
        "venture",
        "valuation",
        "revenue",
        "earnings",
        "profit",
        "acquisition",
        "acquired",
        "merger",
        "partnership",
        "contract",
        "agreement",
        "deal",
        "customer",
        "sales",
        "pricing",
        "production",
        "expansion",
        "expands",
        "expanded",
        "team up",
        "teamed up",
        "explore solutions",
        "production agreement",
    ]

    policy_title_signals = [
        "government",
        "ministry",
        "department",
        "regulator",
        "regulatory",
        "legislation",
        "policy",
        "procurement",
        "national security",
        "defence",
        "defense",
        "military",
        "dod",
        "mod",
        "darpa",
        "diu",
        "sbir",
        "nato",
        "dstl",
        "marine corps",
        "warfighter",
        "us military",
    ]

    product_title_signals = [
        "product",
        "platform",
        "tool",
        "software",
        "api",
        "application",
        "app",
        "model",
        "device",
        "system",
        "service",
        "feature",
        "gateway",
        "robot",
        "drone",
        "vehicle",
        "aircraft",
        "sentry",
        "lattice",
        "mistral",
        "chatgpt",
        "notebooklm",
        "openclaw",
    ]

    strategic_title_signals = [
        "strategy",
        "strategic",
        "market",
        "industry",
        "infrastructure",
        "competition",
        "competitive",
        "ecosystem",
        "platform",
        "scale",
        "scaling",
        "enterprise",
        "geopolitical",
        "national security",
        "supply chain",
        "semiconductor",
        "sovereign",
        "military",
        "defence",
        "defense",
    ]

    release_title_signals = [
        "launch",
        "launches",
        "launched",
        "introducing",
        "introduced",
        "introduction",
        "release",
        "released",
        "unveil",
        "unveiled",
        "debut",
        "debuts",
        "available",
        "adds",
        "added",
        "adding",
        "expands",
        "expanded",
        "expanding",
        "achieves",
        "achieved",
        "awards",
        "awarded",
        "agreement",
        "team up",
        "teams up",
        "showcases",
        "showcase",
        "built",
        "building",
        "delivers",
        "deliver",
        "production",
    ]

    # --------------------------------------------------------------
    # TITLE SIGNAL COUNTS
    # --------------------------------------------------------------

    title_technical_hits = sum(
        1
        for phrase in technical_title_signals
        if phrase in lower_title
    )

    title_business_hits = sum(
        1
        for phrase in business_title_signals
        if phrase in lower_title
    )

    title_policy_hits = sum(
        1
        for phrase in policy_title_signals
        if phrase in lower_title
    )

    title_product_hits = sum(
        1
        for phrase in product_title_signals
        if phrase in lower_title
    )

    title_strategic_hits = sum(
        1
        for phrase in strategic_title_signals
        if phrase in lower_title
    )

    title_release_hits = sum(
        1
        for phrase in release_title_signals
        if phrase in lower_title
    )

    # --------------------------------------------------------------
    # SHARED BODY SIGNALS
    # --------------------------------------------------------------

    technical_signals = [
        "ai",
        "artificial intelligence",
        "llm",
        "large language model",
        "machine learning",
        "deep learning",
        "neural network",
        "inference",
        "training",
        "benchmark",
        "evaluation",
        "rag",
        "retrieval augmented",
        "agentic",
        "agent",
        "agents",
        "robotics",
        "robot",
        "autonomy",
        "autonomous",
        "computer vision",
        "multimodal",
        "algorithm",
        "dataset",
        "architecture",
        "gpu",
        "chip",
        "semiconductor",
        "software",
        "api",
        "cli",
        "developer",
        "engineering",
    ]

    business_signals = [
        "funding",
        "funded",
        "investment",
        "invested",
        "investor",
        "venture",
        "valuation",
        "revenue",
        "earnings",
        "profit",
        "loss",
        "acquisition",
        "acquired",
        "merger",
        "partnership",
        "contract",
        "agreement",
        "deal",
        "customer",
        "customers",
        "sales",
        "pricing",
        "production",
        "expansion",
        "expands",
        "expanded",
        "launches",
        "launched",
        "company",
        "startup",
    ]

    policy_signals = [
        "government",
        "ministry",
        "department",
        "regulator",
        "regulatory",
        "legislation",
        "law",
        "bill",
        "policy",
        "procurement",
        "national security",
        "defence",
        "defense",
        "military",
        "dod",
        "mod",
        "darpa",
        "diu",
        "sbir",
        "nato",
        "dstl",
        "marine corps",
        "warfighter",
        "government contract",
    ]

    product_signals = [
        "product",
        "platform",
        "tool",
        "software",
        "api",
        "application",
        "app",
        "model",
        "device",
        "system",
        "service",
        "feature",
        "gateway",
        "robot",
        "drone",
        "vehicle",
        "aircraft",
    ]

    strategic_signals = [
        "strategy",
        "strategic",
        "market",
        "industry",
        "infrastructure",
        "competition",
        "competitive",
        "ecosystem",
        "platform",
        "scale",
        "scaling",
        "enterprise",
        "geopolitical",
        "national security",
        "supply chain",
        "semiconductor",
        "sovereign",
    ]

    technical_hits = sum(
        1
        for phrase in technical_signals
        if phrase in combined
    )

    business_hits = sum(
        1
        for phrase in business_signals
        if phrase in combined
    )

    policy_hits = sum(
        1
        for phrase in policy_signals
        if phrase in combined
    )

    product_hits = sum(
        1
        for phrase in product_signals
        if phrase in combined
    )

    strategic_hits = sum(
        1
        for phrase in strategic_signals
        if phrase in combined
    )

    # --------------------------------------------------------------
    # PODCAST QUALITY GATE
    # --------------------------------------------------------------

    if source_type == "podcast":
        podcast_intelligence = (
            title_technical_hits
            + title_business_hits
            + title_policy_hits
            + title_product_hits
            + title_strategic_hits
        )

        body_intelligence = (
            technical_hits
            + business_hits
            + policy_hits
            + product_hits
            + strategic_hits
        )

        # A substantive podcast needs either strong title evidence
        # or multiple supporting intelligence signals.
        if (
            podcast_intelligence < 1
            and body_intelligence < 3
        ):
            return 0

        # Generic strategy/career/product-management discussion
        # still needs a concrete technology/company signal.
        if (
            title_strategic_hits > 0
            and title_technical_hits == 0
            and title_product_hits == 0
            and title_business_hits == 0
            and title_policy_hits == 0
            and body_intelligence < 4
        ):
            return 0

    # --------------------------------------------------------------
    # DESK-SPECIFIC INTELLIGENCE GATE
    # --------------------------------------------------------------

    if writer_id == "ravi_chatterjee":
        score = (
            title_technical_hits * 6
            + technical_hits * 2
        )

        if (
            "research" in combined
            or "study" in combined
            or "paper" in combined
            or "benchmark" in combined
            or "evaluation" in combined
            or "evaluating" in combined
        ):
            score += 5

        if title_release_hits and title_technical_hits:
            score += 3

        if technical_hits >= 2:
            score += 3

        return score if score >= 8 else 0

    if writer_id == "tomas_vega":
        score = (
            title_business_hits * 6
            + business_hits * 3
            + title_strategic_hits * 2
            + strategic_hits
        )

        quantitative_terms = [
            "million",
            "billion",
            "%",
            "percent",
            "valuation",
            "revenue",
            "funding",
            "investment",
        ]

        if any(
            term in combined
            for term in quantitative_terms
        ):
            score += 4

        if (
            title_business_hits >= 1
            and (
                title_release_hits
                or title_strategic_hits
            )
        ):
            score += 4

        return score if score >= 8 else 0

    if writer_id == "ingrid_sorensen":
        score = (
            title_policy_hits * 7
            + policy_hits * 3
            + title_strategic_hits * 2
            + strategic_hits
        )

        if (
            "government" in combined
            or "defence" in combined
            or "defense" in combined
            or "national security" in combined
            or "military" in combined
        ):
            score += 4

        if title_policy_hits >= 1:
            score += 3

        return score if score >= 9 else 0

    if writer_id == "dev_okafor":
        score = (
            title_product_hits * 6
            + product_hits * 3
            + title_technical_hits * 2
        )

        if title_release_hits:
            score += 7

        if (
            title_product_hits >= 1
            and title_release_hits >= 1
        ):
            score += 4

        return score if score >= 10 else 0

    if writer_id == "callum_reyes":
        event_terms = [
            "announces",
            "announced",
            "reveals",
            "revealed",
            "reported",
            "reports",
            "departs",
            "arrives",
            "achieves",
            "achieved",
            "wins",
            "fails",
            "opens",
            "closes",
            "expands",
            "launches",
            "awards",
            "awarded",
            "approved",
            "debut",
            "debuts",
        ]

        event_hits = sum(
            1
            for term in event_terms
            if term in lower_title
        )

        score = (
            event_hits * 5
            + title_strategic_hits * 2
            + strategic_hits
        )

        if (
            title_policy_hits
            or title_product_hits
            or title_business_hits
            or title_technical_hits
        ):
            score += 2

        return score if score >= 8 else 0

    return 0


def _coverage_records(coverage):
    if isinstance(coverage, dict):
        values = coverage.values()
    elif isinstance(coverage, list):
        values = [coverage]
    else:
        return []

    found = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("title") or value.get("record_id"):
                found.append(value)

            for child in value.values():
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    for value in values:
        walk(value)

    return found


def _subject_tokens(record):
    title = str(
        record.get("title") or ""
    ).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    stop = {
        "the",
        "and",
        "for",
        "from",
        "with",
        "this",
        "that",
        "into",
        "over",
        "how",
        "why",
        "what",
        "inside",
        "introducing",
        "official",
        "new",
    }

    return {
        token
        for token in title.split()
        if len(token) >= 4
        and token not in stop
    }


def _is_continuation(record, coverage):
    previous = _coverage_records(
        coverage
    )

    if not previous:
        return False, []

    current_tokens = _subject_tokens(
        record
    )

    if len(current_tokens) < 2:
        return False, []

    current_date = _date_value(record)

    matches = []

    for old in previous:
        old_tokens = _subject_tokens(old)

        if len(old_tokens) < 2:
            continue

        overlap = (
            len(
                current_tokens
                & old_tokens
            )
            / max(
                1,
                len(
                    current_tokens
                    | old_tokens
                ),
            )
        )

        if overlap < 0.45:
            continue

        old_date = _date_value(old)

        if (
            current_date is not None
            and old_date is not None
            and current_date <= old_date
        ):
            continue

        matches.append(old)

    return (
        bool(matches),
        matches,
    )


def route_record(record, coverage):
    # Use the single central editorial router so primary desk rules,
    # continuation handling, and the controlled fallback all operate
    # consistently.
    return _assign_best_desk(
        record,
        coverage,
    )


def route_all(records, coverage):
    routes = {
        writer_id: []
        for writer_id in WRITER_IDS
    }

    unrouted = []

    for record in records:
        writer_id = route_record(
            record,
            coverage,
        )

        if writer_id in routes:
            routes[writer_id].append(record)
        else:
            unrouted.append(record)

    return routes, unrouted



def select_candidates(records, coverage):
    routed_result = route_all(
        records,
        coverage,
    )

    if isinstance(routed_result, tuple):
        routed = routed_result[0]
    else:
        routed = routed_result

    candidates = {}

    for writer_id in WRITER_IDS:
        ranked = []

        for record in routed.get(
            writer_id,
            [],
        ):
            record_date = _date_value(record)

            if record_date is not None:
                from datetime import datetime, timezone

                now = datetime.now(timezone.utc)

                if record_date.tzinfo is None:
                    record_date = record_date.replace(
                        tzinfo=timezone.utc
                    )

                age_days = (
                    now - record_date
                ).days

                if age_days > DAILY_CANDIDATE_DAYS:
                    continue

            score, reasons = story_type_score(
                record,
                writer_id,
            )

            if score <= 0:
                continue

            ranked.append(
                (
                    score + _recency_bonus(record) + _newsworthiness_bonus(record),
                    _date_value(record),
                    record,
                )
            )

        ranked.sort(
            key=lambda item: (
                item[0],
                item[1] or 0,
            ),
            reverse=True,
        )

        candidates[writer_id] = [
            item[2]
            for item in ranked[:10]
        ]

    routed_ids = {
        record.get("record_id")
        for desk_records in routed.values()
        for record in desk_records
    }

    candidate_ids = {
        record.get("record_id")
        for desk_records in candidates.values()
        for record in desk_records
    }

    unrouted = [
        record
        for record in records
        if record.get("record_id") not in routed_ids
        and record.get("record_id") not in candidate_ids
    ]

    return candidates, unrouted


def select_for_writer(records):
    """
    Final writer intake.

    The selector has already:
    - classified each record,
    - routed it to exactly one desk,
    - applied the daily freshness window,
    - scored and ranked the desk pool.

    Do not run the removed legacy relevance_score() here.
    Keep the selector's ordering intact.
    """
    return list(records[:RECORDS_PER_WRITER])


# ======================================================================
# GLOBAL STORY / TOPIC MEMORY
# ======================================================================

STORY_MEMORY_FILE = (
    BASE_DIR
    / "data"
    / "editorial"
    / "story_memory.json"
)

GLOBAL_PRIORITY_COUNT = 30
GLOBAL_WIDE_COUNT = 100
GLOBAL_STORY_TARGET = 9

STORY_MEMORY_STOPWORDS = {
    "about", "after", "against", "amid", "among", "around",
    "before", "being", "between", "built", "company", "companies",
    "could", "does", "from", "have", "into", "latest", "more",
    "new", "news", "over", "plans", "report", "reports", "says",
    "said", "their", "there", "these", "this", "through", "under",
    "using", "what", "when", "where", "which", "with", "would",
    "year", "years", "update", "updates", "official", "announcement",
    "government", "technology", "business", "market", "research",
    "product", "policy", "financial", "investment", "results",
    "deal", "study", "follow", "happened", "next",
    "introduces", "introduced", "launches", "launched",
    "announces", "announced",
}

LOW_INFORMATION_TITLES = {
    "submit a proposal",
    "submit proposal",
    "read more",
    "learn more",
    "latest news",
    "news",
    "announcement",
    "update",
    "guidance",
}


def _story_memory_load():
    if not STORY_MEMORY_FILE.exists():
        return []

    try:
        data = json.loads(
            STORY_MEMORY_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return []

    if isinstance(data, dict):
        stories = data.get("stories", [])
        return stories if isinstance(stories, list) else []

    if isinstance(data, list):
        return data

    return []


def _story_memory_save(stories):
    STORY_MEMORY_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "version": 1,
        "updated": datetime.now(
            timezone.utc
        ).isoformat(),
        "stories": stories,
    }

    STORY_MEMORY_FILE.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )


def _story_title_tokens(record):
    if not isinstance(record, dict):
        return set()

    title = str(
        record.get("title")
        or record.get("headline")
        or ""
    ).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    return {
        token
        for token in title.split()
        if len(token) >= 4
        and token not in STORY_MEMORY_STOPWORDS
        and not token.isdigit()
    }


def _story_identifier(record):
    if not isinstance(record, dict):
        return ""

    for key in (
        "development_id",
        "story_id",
        "record_id",
    ):
        value = record.get(key)

        if value:
            return str(value)

    return ""


def _story_signature(record):
    return {
        "record_id": str(
            record.get("record_id") or ""
        ),
        "development_id": str(
            record.get("development_id") or ""
        ),
        "story_id": str(
            record.get("story_id") or ""
        ),
        "title": clean_title(
            record.get("title")
            or record.get("headline")
            or ""
        ).strip(),
        "tokens": sorted(
            _story_title_tokens(record)
        ),
        "date": str(
            record.get("date")
            or record.get("published_at")
            or record.get("published")
            or ""
        ),
    }


def _story_is_low_information(record):
    if not isinstance(record, dict):
        return True

    title = clean_title(
        record.get("title")
        or record.get("headline")
        or ""
    ).strip()

    if not title:
        return True

    if title.lower() in LOW_INFORMATION_TITLES:
        return True

    return len(
        _story_title_tokens(record)
    ) < 2


def _story_similarity(current, old):
    if not isinstance(current, dict):
        return 0.0

    if not isinstance(old, dict):
        return 0.0

    current_ids = {
        str(current.get("development_id") or ""),
        str(current.get("story_id") or ""),
        str(current.get("record_id") or ""),
    }

    old_ids = {
        str(old.get("development_id") or ""),
        str(old.get("story_id") or ""),
        str(old.get("record_id") or ""),
    }

    current_ids.discard("")
    old_ids.discard("")

    if current_ids & old_ids:
        return 1.0

    current_tokens = _story_title_tokens(current)

    old_tokens = set(
        old.get("tokens") or []
    )

    if not old_tokens:
        old_tokens = {
            token
            for token in re.findall(
                r"[a-z0-9][a-z0-9'-]{3,}",
                str(old.get("title") or "").lower(),
            )
            if token not in STORY_MEMORY_STOPWORDS
        }

    if not current_tokens or not old_tokens:
        return 0.0

    intersection = (
        current_tokens & old_tokens
    )

    union = (
        current_tokens | old_tokens
    )

    similarity = (
        len(intersection)
        / max(1, len(union))
    )

    if similarity >= 0.50:
        return 1.0

    distinctive = {
        token
        for token in intersection
        if len(token) >= 6
    }

    if distinctive and len(intersection) >= 2:
        return 0.90

    if distinctive and similarity >= 0.30:
        return 0.80

    return similarity


def _story_already_covered(record, memory):
    for old in memory:
        if _story_similarity(
            record,
            old,
        ) >= 0.80:
            return True, old

    return False, None


def _candidate_rank(record, writer_id):
    score, reasons = story_type_score(
        record,
        writer_id,
    )

    minimum = DESK_MINIMUM_SCORE.get(
        writer_id,
        999,
    )

    if score < minimum:
        return None

    record_date = _date_value(record)

    if record_date is not None:
        now = datetime.now(timezone.utc)

        if record_date.tzinfo is None:
            record_date = record_date.replace(
                tzinfo=timezone.utc
            )

        age_days = (
            now - record_date
        ).days

        if age_days > DAILY_CANDIDATE_DAYS:
            return None

    return (
        score + _recency_bonus(record) + _newsworthiness_bonus(record),
        record_date,
        reasons,
    )


def build_global_candidate_pool(records, coverage):
    """
    Build the global newsroom candidate pool.

    Routing is authoritative.

    Once route_all() has assigned a record to a specialist desk,
    the record must remain available to that desk unless it is:

    - already covered in story memory,
    - too old for the daily candidate window, or
    - genuinely low-information.

    We do NOT re-apply the desk minimum score here. That caused
    correctly routed specialist stories to disappear before the
    writers ever saw them.
    """

    routed_result = route_all(
        records,
        coverage,
    )

    if isinstance(routed_result, tuple):
        routed = routed_result[0]
        unrouted = routed_result[1]
    else:
        routed = routed_result
        unrouted = []

    ranked = []
    seen_ids = set()
    story_memory = _story_memory_load()

    for writer_id in WRITER_IDS:
        for record in routed.get(
            writer_id,
            [],
        ):
            record_id = str(
                record.get("record_id") or ""
            )

            if record_id and record_id in seen_ids:
                continue

            if _story_is_low_information(record):
                continue

            covered, old_story = _story_already_covered(
                record,
                story_memory,
            )

            if covered:
                print(
                    "  MEMORY REJECT: "
                    + clean_title(
                        record.get("title")
                    )
                )
                continue

            record_date = _date_value(record)

            if record_date is not None:
                now = datetime.now(timezone.utc)

                if record_date.tzinfo is None:
                    record_date = record_date.replace(
                        tzinfo=timezone.utc
                    )

                age_days = (
                    now - record_date
                ).days

                if age_days > DAILY_CANDIDATE_DAYS:
                    continue

            # Routing is authoritative.
            #
            # Use the specialist score only for ranking, never
            # for deciding whether an already-routed record survives.
            score, reasons = story_type_score(
                record,
                writer_id,
            )

            if score <= 0:
                score = 1
                reasons = [
                    "authoritative specialist routing"
                ]

            score += _recency_bonus(record) + _newsworthiness_bonus(record)

            if record_id:
                seen_ids.add(record_id)

            ranked.append(
                {
                    "record": record,
                    "writer_id": writer_id,
                    "score": score,
                    "date": record_date,
                    "reasons": reasons,
                }
            )

    ranked.sort(
        key=lambda item: (
            item["score"],
            item["date"] or 0,
        ),
        reverse=True,
    )

    return ranked, unrouted


def _hard_specialist_route(record):
    """
    High-confidence specialist routing.

    These rules deliberately require strong subject evidence.
    They run before the general editorial scoring system so that
    specialist desks own stories that are clearly about their domain.
    """

    title = str(
        record.get("title")
        or record.get("name")
        or record.get("headline")
        or ""
    ).lower()

    body = str(
        record.get("summary")
        or record.get("description")
        or record.get("abstract")
        or record.get("content")
        or record.get("text")
        or ""
    ).lower()

    combined = f"{title} {body}"

    # ------------------------------------------------------------
    # ELENA ? DRONES & UNCREWED SYSTEMS
    # ------------------------------------------------------------
    elena_patterns = [
        r"\buav\b",
        r"\buas\b",
        r"\bcuas\b",
        r"counter[- ]uav",
        r"counter[- ]uas",
        r"counter[- ]drone",
        r"drone swarm",
        r"drone swarms",
        r"drone warfare",
        r"uncrewed aircraft",
        r"unmanned aircraft",
        r"uncrewed aerial",
        r"unmanned aerial",
        r"autonomous aircraft",
        r"loitering munition",
        r"loitering munitions",
        r"underwater drone",
        r"underwater drones",
        r"uncrewed underwater",
        r"unmanned underwater",
        r"autonomous underwater vehicle",
        r"\bauv\b",
        r"sea drone",
        r"sea drones",
        r"maritime drone",
        r"maritime drones",
        r"eVTOL",
    ]

    if any(re.search(pattern, title) for pattern in elena_patterns):
        return "elena_vasquez"

    # Strong body evidence can also qualify, but requires multiple
    # signals so a passing mention of a drone does not hijack a story.
    elena_hits = sum(
        1
        for pattern in elena_patterns
        if re.search(pattern, combined)
    )

    if elena_hits >= 2:
        return "elena_vasquez"

    # ------------------------------------------------------------
    # MARCUS ? ROBOTICS
    # ------------------------------------------------------------
    marcus_patterns = [
        r"\brobot\b",
        r"\brobots\b",
        r"\brobotics\b",
        r"humanoid",
        r"humanoid robot",
        r"robot learning",
        r"robot manipulation",
        r"robotic manipulation",
        r"embodied ai",
        r"embodied intelligence",
        r"dexterous robot",
        r"dexterous manipulation",
        r"industrial robot",
        r"warehouse robot",
        r"robotic system",
        r"robotic systems",
        r"robot autonomy",
    ]

    if any(re.search(pattern, title) for pattern in marcus_patterns):
        return "marcus_okafor"

    marcus_hits = sum(
        1
        for pattern in marcus_patterns
        if re.search(pattern, combined)
    )

    if marcus_hits >= 2:
        return "marcus_okafor"

    # ------------------------------------------------------------
    # KENJI ? AUTONOMOUS VEHICLES
    # ------------------------------------------------------------
    kenji_patterns = [
        r"self[- ]driving",
        r"self driving",
        r"autonomous vehicle",
        r"autonomous vehicles",
        r"autonomous driving",
        r"driverless",
        r"robotaxi",
        r"robotaxis",
        r"autonomous truck",
        r"autonomous trucks",
        r"autonomous delivery",
        r"autonomous mobility",
        r"vehicle autonomy",
        r"vehicle autonomous",
        r"autonomous fleet",
        r"autonomous fleets",
        r"waymo",
        r"zoox",
        r"cruise",
    ]

    if any(re.search(pattern, title) for pattern in kenji_patterns):
        return "kenji_nakamura"

    kenji_hits = sum(
        1
        for pattern in kenji_patterns
        if re.search(pattern, combined)
    )

    if kenji_hits >= 2:
        return "kenji_nakamura"

    # ------------------------------------------------------------
    # SOFIA ? INDUSTRIAL SYSTEMS & INFRASTRUCTURE
    # ------------------------------------------------------------
    sofia_patterns = [
        r"semiconductor fab",
        r"semiconductor fabrication",
        r"chip fabrication",
        r"chip fab",
        r"fabrication plant",
        r"\bfoundry\b",
        r"\bwafer\b",
        r"data cent(?:er|re)",
        r"data centres",
        r"data centers",
        r"hyperscale",
        r"manufacturing",
        r"manufacture",
        r"manufactured",
        r"factory",
        r"factories",
        r"production facility",
        r"production facilities",
        r"production plant",
        r"industrial automation",
        r"industrial system",
        r"industrial systems",
        r"production capacity",
        r"manufacturing capacity",
        r"supply chain",
        r"mass production",
        r"large[- ]scale production",
        r"production line",
        r"production lines",
        r"industrial infrastructure",
        r"energy infrastructure",
    ]

    if any(re.search(pattern, title) for pattern in sofia_patterns):
        return "sofia_lindqvist"

    sofia_hits = sum(
        1
        for pattern in sofia_patterns
        if re.search(pattern, combined)
    )

    if sofia_hits >= 2:
        return "sofia_lindqvist"

    # ------------------------------------------------------------
    # RAVI ? AI / COMPUTING / MODELS
    # ------------------------------------------------------------
    ravi_patterns = [
        r"\bllm\b",
        r"\bllms\b",
        r"large language model",
        r"language model",
        r"foundation model",
        r"multimodal model",
        r"generative ai",
        r"machine learning",
        r"deep learning",
        r"inference",
        r"model training",
        r"model architecture",
        r"neural network",
        r"transformer",
        r"diffusion model",
        r"gpu",
        r"accelerator",
        r"ai chip",
        r"ai model",
        r"mistral",
        r"voxtral",
        r"leanstral",
        r"codestral",
        r"ministral",
        r"shieldstral",
        r"robostral",
        r"open[- ]source model",
        r"open source model",
    ]

    if any(re.search(pattern, title) for pattern in ravi_patterns):
        return "ravi_chatterjee"

    ravi_hits = sum(
        1
        for pattern in ravi_patterns
        if re.search(pattern, combined)
    )

    if ravi_hits >= 2:
        return "ravi_chatterjee"

    return None


def _assign_best_desk(record, coverage):
    hard_route = _hard_specialist_route(record)

    if hard_route:
        return hard_route

    choices = []

    for writer_id in (
        "callum_reyes",
        "tomas_vega",
        "ingrid_sorensen",
        "dev_okafor",
        "ravi_chatterjee",
        "elena_vasquez",
        "marcus_okafor",
        "kenji_nakamura",
        "sofia_lindqvist",
    ):
        ranking = _candidate_rank(
            record,
            writer_id,
        )

        if ranking is None:
            continue

        score, record_date, reasons = ranking

        choices.append(
            (
                score,
                record_date or 0,
                writer_id,
            )
        )

    if choices:
        choices.sort(
            key=lambda item: (
                item[0],
                item[1],
            ),
            reverse=True,
        )

        return choices[0][2]

    # Primary desk rules deliberately remain strict.
    # If none qualify, use the softer editorial fallback.
    fallback_choices = []

    for writer_id in (
        "ingrid_sorensen",
        "elena_vasquez",
        "marcus_okafor",
        "kenji_nakamura",
        "sofia_lindqvist",
        "dev_okafor",
        "tomas_vega",
        "callum_reyes",
        "ravi_chatterjee",
    ):
        score, reasons = editorial_fallback_score(
            record,
            writer_id,
        )

        if score <= 0:
            continue

        record_date = _date_value(record)

        if record_date is not None:
            now = datetime.now(timezone.utc)

            if record_date.tzinfo is None:
                record_date = record_date.replace(
                    tzinfo=timezone.utc
                )

        fallback_choices.append(
            (
                score,
                record_date or 0,
                writer_id,
            )
        )

    if fallback_choices:
        fallback_choices.sort(
            key=lambda item: (
                item[0],
                item[1],
            ),
            reverse=True,
        )

        return fallback_choices[0][2]

    # Final controlled intelligence gate.
    # This catches valuable records that contain genuine
    # technology, business, policy, product or strategic
    # intelligence without weakening the primary rules.
    intelligence_choices = []

    for writer_id in (
        "ingrid_sorensen",
        "dev_okafor",
        "tomas_vega",
        "callum_reyes",
        "ravi_chatterjee",
    ):
        score = intelligence_gate_score(
            record,
            writer_id,
        )

        if score <= 0:
            continue

        record_date = _date_value(record)

        if record_date is not None:
            now = datetime.now(timezone.utc)

            if record_date.tzinfo is None:
                record_date = record_date.replace(
                    tzinfo=timezone.utc
                )

        intelligence_choices.append(
            (
                score,
                record_date or 0,
                writer_id,
            )
        )

    if not intelligence_choices:
        return None

    intelligence_choices.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )

    return intelligence_choices[0][2]


def select_global_stories(records, coverage):
    """
    Build the daily intake for all nine specialist journalists.

    Architecture:
        intelligence -> specialist routing -> one story per desk
        -> journalist research -> journalist article -> Maren
        -> Yuki ranking -> Dana distribution.

    Each desk gets one story whenever a suitable unused record exists.
    Specialist routing remains authoritative, but empty desks are given
    a second-chance search across the full intelligence pool using
    desk-specific signals.

    Yuki is the final editorial ranking layer.
    """

    memory = _story_memory_load()

    routed_result = route_all(
        records,
        coverage,
    )

    if isinstance(routed_result, tuple):
        routed = routed_result[0]
        unrouted = routed_result[1]
    else:
        routed = routed_result
        unrouted = []

    print()
    print("SPECIALIST DESK STORY SELECTION")
    print("-" * 70)
    print(
        f"Story memory: {len(memory)} published stories"
    )

    selected_records = []
    selected = []
    allocated = {
        writer_id: []
        for writer_id in WRITER_IDS
    }

    def eligible(record):
        if _story_is_low_information(record):
            return False

        covered, old_story = _story_already_covered(
            record,
            memory,
        )

        if covered:
            return False

        record_date = _date_value(record)

        if record_date is not None:
            now = datetime.now(timezone.utc)

            if record_date.tzinfo is None:
                record_date = record_date.replace(
                    tzinfo=timezone.utc
                )

            age_days = (
                now - record_date
            ).days

            if age_days > DAILY_CANDIDATE_DAYS:
                return False

        return True

    def already_selected(record):
        for chosen_record in selected_records:
            if _story_similarity(
                record,
                chosen_record,
            ) >= 0.80:
                return True

        return False

    # --------------------------------------------------------------
    # PASS 1 — authoritative specialist routing
    # --------------------------------------------------------------

    for writer_id in WRITER_IDS:
        desk_candidates = []

        for record in routed.get(
            writer_id,
            [],
        ):
            if not eligible(record):
                continue

            score, reasons = story_type_score(
                record,
                writer_id,
            )

            if score <= 0:
                score = 1
                reasons = [
                    "authoritative specialist routing"
                ]

            score += _recency_bonus(record) + _newsworthiness_bonus(record)

            desk_candidates.append(
                {
                    "record": record,
                    "writer_id": writer_id,
                    "score": score,
                    "date": _date_value(record),
                    "reasons": reasons,
                }
            )

        desk_candidates.sort(
            key=lambda item: (
                item["score"],
                item["date"] or 0,
            ),
            reverse=True,
        )

        for item in desk_candidates:
            record = item["record"]

            if already_selected(record):
                continue

            selected_records.append(record)
            selected.append(item)
            allocated[writer_id].append(record)

            print(
                f"  SELECTED {len(selected)}. "
                f"{clean_title(record.get('title'))}"
                f" -> {WRITERS[writer_id]['name']}"
            )

            break

    # --------------------------------------------------------------
    # PASS 2 — rescue empty desks from the full intelligence pool
    # --------------------------------------------------------------

    # These patterns are deliberately broad. The journalist will do
    # the actual web research after receiving the selected topic.
    rescue_patterns = {
        "callum_reyes": [
            r"news", r"announce", r"launch", r"report",
            r"event", r"agreement", r"statement",
            r"investigation", r"research",
        ],
        "tomas_vega": [
            r"fund", r"funding", r"investment", r"investor",
            r"revenue", r"market", r"business", r"company",
            r"contract", r"deal", r"acquisition", r"customer",
            r"partnership", r"finance", r"financial",
        ],
        "ingrid_sorensen": [
            r"government", r"defence", r"defense", r"military",
            r"policy", r"regulation", r"procurement", r"ministry",
            r"nato", r"mod", r"dod", r"darpa", r"legislation",
            r"security", r"national", r"strategic",
        ],
        "dev_okafor": [
            r"product", r"platform", r"app", r"software",
            r"release", r"feature", r"tool", r"service",
            r"customer", r"user", r"chatgpt", r"api",
            r"browser", r"developer",
        ],
        "ravi_chatterjee": [
            r"llm", r"language model", r"foundation model",
            r"machine learning", r"deep learning", r"transformer",
            r"neural", r"inference", r"training", r"benchmark",
            r"arxiv", r"research", r"algorithm", r"architecture",
            r"gpu", r"chip", r"semiconductor", r"ai",
        ],
        "elena_vasquez": [
            r"drone", r"uav", r"uas", r"cuas",
            r"uncrewed", r"unmanned", r"loitering",
            r"autonomous aircraft", r"sea drone",
            r"underwater vehicle", r"counter[- ]drone",
        ],
        "marcus_okafor": [
            r"robot", r"robotics", r"humanoid",
            r"manipulation", r"embodied", r"dexterous",
            r"robotic", r"physical ai",
        ],
        "kenji_nakamura": [
            r"waymo", r"zoox", r"cruise",
            r"robotaxi", r"self[- ]driving",
            r"autonomous vehicle", r"autonomous driving",
            r"driverless", r"autonomous truck",
            r"autonomous fleet", r"vehicle autonomy",
        ],
        "sofia_lindqvist": [
            r"factory", r"factories", r"manufacturing",
            r"production", r"plant", r"facility",
            r"semiconductor fab", r"foundry", r"wafer",
            r"supply chain", r"infrastructure",
            r"data cent(?:er|re)", r"hyperscale",
            r"industrial", r"capacity", r"energy",
        ],
    }

    def rescue_score(record, writer_id):
        title = str(
            record.get("title")
            or record.get("name")
            or record.get("headline")
            or ""
        ).lower()

        body = str(
            record.get("summary")
            or record.get("description")
            or record.get("abstract")
            or record.get("content")
            or record.get("text")
            or ""
        ).lower()

        combined = f"{title} {body}"

        score = 0

        for pattern in rescue_patterns.get(
            writer_id,
            [],
        ):
            if re.search(pattern, title):
                score += 12
            elif re.search(pattern, combined):
                score += 4

        score += _recency_bonus(record) + _newsworthiness_bonus(record)

        return score

    for writer_id in WRITER_IDS:
        if allocated[writer_id]:
            continue

        rescue_candidates = []

        for record in records:
            if not eligible(record):
                continue

            if already_selected(record):
                continue

            score = rescue_score(
                record,
                writer_id,
            )

            if score <= 0:
                continue

            rescue_candidates.append(
                (
                    score,
                    _date_value(record) or 0,
                    record,
                )
            )

        rescue_candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
            ),
            reverse=True,
        )

        if rescue_candidates:
            score, record_date, record = (
                rescue_candidates[0]
            )

            selected_records.append(record)
            selected.append(
                {
                    "record": record,
                    "writer_id": writer_id,
                    "score": score,
                    "date": _date_value(record),
                    "reasons": [
                        "empty-desk rescue routing"
                    ],
                }
            )
            allocated[writer_id].append(record)

            print(
                f"  RESCUED {len(selected)}. "
                f"{clean_title(record.get('title'))}"
                f" -> {WRITERS[writer_id]['name']}"
            )
        else:
            print(
                f"  NO SUITABLE STORY -> "
                f"{WRITERS[writer_id]['name']}"
            )

    print()
    print(
        f"Fresh distinct stories selected: "
        f"{len(selected)}"
    )

    print()
    print("GLOBAL DESK ALLOCATION")
    print("-" * 70)

    for writer_id in WRITER_IDS:
        print(
            f"  {WRITERS[writer_id]['name']}: "
            f"{len(allocated[writer_id])}"
        )

    return allocated, unrouted, selected

def record_successful_story_memory(result):
    memory = _story_memory_load()

    selected = result.get(
        "selected_records",
        [],
    )

    journalist_id = result.get(
        "journalist_id",
        "",
    )

    for record in selected:
        signature = _story_signature(
            record
        )

        already = False

        for old in memory:
            if (
                signature["development_id"]
                and signature["development_id"]
                == old.get("development_id")
            ):
                already = True
                break

            if (
                signature["story_id"]
                and signature["story_id"]
                == old.get("story_id")
            ):
                already = True
                break

        if already:
            continue

        memory.append(
            {
                **signature,
                "desk": journalist_id,
                "journalist": result.get(
                    "journalist",
                    "",
                ),
                "published": True,
                "verified": True,
                "memory_added": datetime.now(
                    timezone.utc
                ).isoformat(),
            }
        )

    _story_memory_save(memory)


# OLLAMA
# ======================================================================

def ollama_generate(prompt):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_ctx": 8192,
        },
    }

    started = time.time()

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=OLLAMA_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    output = normalise_text(
        data.get("response")
    )

    elapsed = round(
        time.time() - started,
        1,
    )

    print(
        f"  Local AI completed in {elapsed}s"
    )

    return output


def openai_generate(prompt, fallback_to_ollama=True):
    """Write with OpenAI; optionally fall back to local Ollama."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not api_key:
        env_path = BASE_DIR / ".env"
        if env_path.is_file():
            for line in env_path.read_text(
                encoding="utf-8-sig"
            ).splitlines():
                candidate = line.strip()
                if candidate.startswith("export "):
                    candidate = candidate[7:].strip()
                if candidate.startswith("OPENAI_API_KEY="):
                    api_key = candidate.split("=", 1)[1].strip()
                    if len(api_key) >= 2 and api_key[0] == api_key[-1] and api_key[0] in ("'", '"'):
                        api_key = api_key[1:-1]
                    if api_key:
                        break

    if not api_key:
        message = "OPENAI_API_KEY not found in environment or root .env."
        if fallback_to_ollama:
            print("  OPENAI: " + message + " Falling back to Ollama.")
            return ollama_generate(prompt)
        raise RuntimeError(message)

    started = time.time()
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "input": prompt,
                "max_output_tokens": OPENAI_MAX_OUTPUT_TOKENS,
            },
            timeout=OPENAI_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        output = normalise_text(data.get("output_text", ""))
        if not output:
            chunks = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in ("output_text", "text"):
                        chunks.append(content.get("text", ""))
            output = normalise_text("\n".join(chunks))

        if not output:
            raise RuntimeError("OpenAI returned no article text.")

        elapsed = round(time.time() - started, 1)
        print(f"  OpenAI ({OPENAI_MODEL}) completed in {elapsed}s")
        return output

    except Exception as exc:
        if not fallback_to_ollama:
            raise
        print(f"  OPENAI ERROR: {exc}")
        print("  Falling back to local Ollama for this request.")
        return ollama_generate(prompt)


def extract_json(text):
    if not text:
        return None

    cleaned = text.strip()

    cleaned = re.sub(
        r"^```json\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"^```\s*",
        "",
        cleaned,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    match = re.search(
        r"\{.*\}",
        cleaned,
        flags=re.DOTALL,
    )

    if match:
        try:
            return json.loads(
                match.group(0)
            )
        except Exception:
            return None

    return None


# ======================================================================
# DESK-SPECIFIC LIVE WEB RESEARCH
# ======================================================================

WEB_RESEARCH_CONFIG = {
    "callum_reyes": [
        '"{title}"',
        '"{title}" latest',
        '"{title}" official announcement',
    ],
    "tomas_vega": [
        '"{title}" company business',
        '"{title}" financial market',
        '"{title}" deal investment funding',
    ],
    "ingrid_sorensen": [
        '"{title}" government regulation',
        '"{title}" legislation policy',
        '"{title}" defence procurement official',
    ],
    "dev_okafor": [
        '"{title}" product technology',
        '"{title}" official announcement',
        '"{title}" documentation release',
    ],
    "ravi_chatterjee": [
        '"{title}" research paper',
        '"{title}" study researchers',
        '"{title}" arxiv technical',
    ],
    "elena_vasquez": [
        '"{title}" drone uncrewed',
        '"{title}" UAV UAS autonomous',
        '"{title}" defence deployment capability',
    ],
    "marcus_okafor": [
        '"{title}" robotics',
        '"{title}" robot research',
        '"{title}" robotic system technical',
    ],
    "kenji_nakamura": [
        '"{title}" autonomous vehicle',
        '"{title}" self-driving robotaxi',
        '"{title}" deployment testing',
    ],
    "sofia_lindqvist": [
        '"{title}" manufacturing production',
        '"{title}" factory infrastructure',
        '"{title}" capacity supply chain',
    ],
}


def fetch_web_page(url, max_chars=12000):
    """
    Fetch a public webpage and extract useful textual content.

    Search snippets are leads, not reporting evidence.
    The journalist needs the actual page text wherever possible.
    """
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/154.0 Safari/537.36"
                )
            },
        )

        if response.status_code != 200:
            return ""

        content_type = (
            response.headers.get("content-type") or ""
        ).lower()

        if (
            "text/html" not in content_type
            and "application/xhtml" not in content_type
        ):
            return ""

        html = response.text

        # Remove non-content sections.
        html = re.sub(
            r"<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>",
            " ",
            html,
            flags=re.I | re.S,
        )

        # Remove remaining HTML tags.
        html = re.sub(
            r"<[^>]+>",
            " ",
            html,
        )

        # Decode common HTML entities.
        html = (
            html.replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&quot;", '"')
                .replace("&#39;", "'")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
        )

        # Normalise whitespace.
        html = re.sub(
            r"\s+",
            " ",
            html,
        ).strip()

        if not html:
            return ""

        return html[:max_chars]

    except Exception:
        return ""


def run_web_research(writer_id, selected):
    """
    Research the assigned story on the live web.

    The intelligence record is the assignment lead.
    Search results are only discovery material.
    Actual webpage text is the reporting material.

    The journalist remains locked to selected[0].
    """
    if not selected:
        return []

    record = selected[0]

    if not isinstance(record, dict):
        return []

    title = clean_title(
        record.get("title")
    ).strip()

    if not title:
        return []

    queries = WEB_RESEARCH_CONFIG.get(
        writer_id,
        [
            '"{title}"',
            '"{title}" latest',
            '"{title}" official',
        ],
    )

    results = []
    seen_urls = set()

    try:
        with DDGS() as ddgs:

            for template in queries[:3]:

                query = template.format(
                    title=title
                )

                print(
                    f"    SEARCH: {query}"
                )

                try:
                    found = ddgs.text(
                        query,
                        region="uk-en",
                        max_results=5,
                    )
                except Exception as exc:
                    print(
                        f"    SEARCH ERROR: {exc}"
                    )
                    continue

                if not found:
                    continue

                for item in found:

                    if not isinstance(item, dict):
                        continue

                    url = (
                        item.get("href")
                        or item.get("url")
                        or ""
                    ).strip()

                    if not url:
                        continue

                    if url in seen_urls:
                        continue

                    seen_urls.add(url)

                    search_title = (
                        item.get("title")
                        or ""
                    )

                    snippet = (
                        item.get("body")
                        or item.get("snippet")
                        or ""
                    )

                    print(
                        f"    FETCH: {search_title[:100]}"
                    )

                    page_text = fetch_web_page(
                        url
                    )

                    results.append(
                        {
                            "query": query,
                            "title": search_title,
                            "url": url,
                            "snippet": snippet,
                            "page_text": page_text,
                            "page_text_length": len(page_text),
                        }
                    )

                    # Five useful sources is enough for
                    # a single local-model journalist.
                    if len(results) >= 5:
                        return results

    except Exception as exc:
        print(
            f"    WEB RESEARCH UNAVAILABLE: {exc}"
        )

    return results


def format_web_research(research_packet):
    if not research_packet:
        return (
            "NO LIVE WEB RESEARCH RESULTS WERE RETURNED. "
            "DO NOT INVENT MISSING FACTS."
        )

    return json.dumps(
        research_packet,
        ensure_ascii=False,
        indent=2,
    )


# ======================================================================
# WRITER PROMPT
# ======================================================================

def writer_prompt(writer_id, records, previous, research_packet=None):
    """
    Build a compact, evidence-led specialist journalist assignment.

    RECORD #1 is always the assigned story.
    Additional records are supporting context only.
    Live research supports the assigned story but cannot replace it.
    """

    writer = WRITERS[writer_id]

    records = list(records or [])

    if not records:
        raise ValueError(
            f"No intelligence records supplied to {writer_id}."
        )

    assigned_story = records[0]
    supporting_records = records[1:]

    assigned_intelligence = compact_record(
        assigned_story
    )

    supporting_intelligence = [
        compact_record(record)
        for record in supporting_records
    ]

    # Keep live research useful without dumping enormous webpage
    # captures into the model context.
    compact_research = []

    for item in (research_packet or []):
        if not isinstance(item, dict):
            continue

        compact_research.append(
            {
                "query": item.get("query", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": str(
                    item.get("snippet", "")
                )[:700],
                "page_text": str(
                    item.get("page_text", "")
                )[:3500],
            }
        )

    research_text = json.dumps(
        compact_research,
        ensure_ascii=False,
        indent=2,
    )

    supporting_text = json.dumps(
        supporting_intelligence,
        ensure_ascii=False,
        indent=2,
    )

    assigned_text = json.dumps(
        assigned_intelligence,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
MACHINA DAILY — SPECIALIST JOURNALIST

You are {writer["name"]}, Machina Daily's {writer["role"]}.

SPECIALIST APPROACH:
{writer["instruction"]}

============================================================
ASSIGNED STORY — THIS IS THE ONLY STORY
============================================================

{assigned_text}

The record above is your assignment.

Write about THIS story.

The headline, opening and entire article must remain about the
same subject identified by the assigned record.

Supporting records and web research are evidence only.
They must NEVER become a replacement story.

If evidence concerns a different company, technology, paper,
product, programme or event, ignore it.

============================================================
SUPPORTING INTELLIGENCE
============================================================

{supporting_text}

Use supporting intelligence only when it directly helps explain,
confirm or contextualise the assigned story.

============================================================
LIVE RESEARCH
============================================================

{research_text}

Use the supplied research as reporting evidence.

Before using a source, verify that it actually concerns the
assigned story rather than merely sharing a keyword.

Prefer fetched page text over search-result snippets.

Do not use general model knowledge to fill gaps.

============================================================
EVIDENCE RULES
============================================================

Write only what is established by the supplied intelligence
and directly relevant research.

Do NOT invent:

- people or organisations
- dates
- numbers or performance figures
- capabilities
- customers or users
- funding or investment
- contracts
- deployments
- demonstrations
- quotations
- market reactions
- policy decisions
- technical results

Do not interpret an unlabeled number.

Do not expand an acronym from memory.

Do not turn an inference into a fact.

If evidence is sparse, write a shorter factual article rather
than inventing detail.

Preserve technical terminology exactly as supported by the evidence.

============================================================
EDITORIAL TASK
============================================================

Write one finished Machina Daily specialist article.

Follow the word limit specified in this journalist's specialist instructions. Do not apply a universal article length.

Do not use a fixed universal article structure.
Let the specialist discipline and evidence determine the shape.

The article should be:

- precise
- readable
- evidence-led
- technically careful
- original in wording
- useful to an intelligent reader

Write like a specialist journalist, not like an AI completing
a worksheet.

Do not begin with generic phrases such as:
"Based on the provided data..."
"The research shows..."
"This article discusses..."

Do not add unsupported "why it matters" claims.

Do not manufacture a conclusion.

============================================================
FINAL SUBJECT CHECK
============================================================

Before returning the article, silently verify:

1. HEADLINE SUBJECT = ASSIGNED STORY
2. BODY SUBJECT = ASSIGNED STORY
3. WEB RESEARCH = ACTUALLY RELEVANT TO ASSIGNED STORY
4. EVERY IMPORTANT CLAIM = SUPPORTED
5. NO INVENTED FACTS
6. NO TECHNICAL TERM HAS BEEN REINTERPRETED
7. ARTICLE LENGTH MUST FOLLOW THIS JOURNALIST'S SPECIALIST INSTRUCTIONS.

If any check fails, rewrite before returning.

============================================================
OUTPUT
============================================================

Return ONLY the finished article.

No commentary.
No analysis.
No source notes.
No validation notes.
No explanation.
No markdown code fence.
"""


# ======================================================================
# WRITER VALIDATION
# ======================================================================

FORBIDDEN_GENERIC = [
    "are getting bigger",
    "is getting bigger",
    "are becoming more powerful",
    "is becoming more powerful",
    "consume more energy",
    "consumes more energy",
    "energy demands are growing",
    "energy demand is growing",
    "the demands of ai are growing",
    "the energy demands of ai are increasing",
    "typical desktop",
    "typical laptop",
    "typical computer",
    "typical consumer hardware",
    "on your typical",
    "more work is needed",
    "more research is needed",
    "crucial area to study",
    "important area to study",
    "as ai continues to grow",
    "as ai grows",
    "as artificial intelligence grows",
    "increasing use of ai",
    "growing use of ai",
    "growing adoption of ai",
]


def validate_writer_output(
    writer_id,
    article,
    records,
):
    """
    Lightweight structural/persona validation.

    The writer prompt is responsible for the requested length,
    sentence structure and editorial form.

    This validator should catch genuinely malformed or unsafe
    output, not reject useful journalism because a local model
    produced a few extra words or a sentence boundary that differs
    from the prompt.

    Maren remains the substantive verification gate.
    """

    issues = []

    article = str(
        article
        or ""
    ).strip()

    lower = article.lower()

    # --------------------------------------------------------------
    # BASIC OUTPUT CHECKS
    # --------------------------------------------------------------

    if not article:
        issues.append(
            "empty bulletin"
        )
        return False, issues

    words = article.split()

    if len(words) < 8:
        issues.append(
            "bulletin is too short"
        )

    # A generous hard ceiling prevents runaway model output while
    # allowing normal variation around each writer's requested target.
    #
    # Individual writer prompts remain authoritative for the intended
    # length. This is only a safety ceiling.
    hard_word_ceiling = {
        "callum_reyes": 400,
        "tomas_vega": 300,
        "ingrid_sorensen": 300,
        "dev_okafor": 300,
        "ravi_chatterjee": 300,
        "elena_vasquez": 300,
        "marcus_okafor": 300,
        "kenji_nakamura": 300,
        "sofia_lindqvist": 300,
    }.get(
        writer_id,
        450,
    )

    if len(words) > hard_word_ceiling:
        issues.append(
            f"over safety ceiling of {hard_word_ceiling} words"
        )

    # --------------------------------------------------------------
    # SENTENCE CHECK
    # --------------------------------------------------------------
    #
    # Do NOT enforce desk-specific sentence counts here.
    #
    # Local models frequently produce abbreviations, decimal values,
    # source names and other punctuation that make naive sentence
    # counting unreliable.
    #
    # The writer prompt controls sentence structure.
    # Maren checks whether the resulting bulletin is actually sound.
    # --------------------------------------------------------------

    # --------------------------------------------------------------
    # PROHIBITED GENERIC FILLER
    # --------------------------------------------------------------

    prohibited_phrases = [
        "are getting bigger",
        "is getting bigger",
        "are becoming more powerful",
        "is becoming more powerful",
        "consume more energy",
        "consumes more energy",
        "energy demands are growing",
        "energy demand is growing",
        "the demands of ai are growing",
        "the energy demands of ai are increasing",
        "typical desktop",
        "typical laptop",
        "typical computer",
        "typical consumer hardware",
        "on your typical",
    ]

    for phrase in prohibited_phrases:
        if phrase in lower:
            issues.append(
                f"contains prohibited generic filler: {phrase}"
            )

    # --------------------------------------------------------------
    # PROHIBITED WORD
    # --------------------------------------------------------------

    if re.search(
        r"\bjust\b",
        lower,
    ):
        issues.append(
            "contains prohibited word just"
        )

    # --------------------------------------------------------------
    # OBVIOUS MODEL META-TEXT
    # --------------------------------------------------------------

    meta_phrases = [
        "as an ai",
        "as a language model",
        "i cannot",
        "i can't",
        "i am unable",
        "here is the article",
        "here's the article",
        "according to the prompt",
        "the user asked",
        "the instructions say",
    ]

    for phrase in meta_phrases:
        if phrase in lower:
            issues.append(
                f"contains model meta-text: {phrase}"
            )

    # --------------------------------------------------------------
    # OBVIOUS MARKDOWN / RESPONSE WRAPPER
    # --------------------------------------------------------------

    if article.startswith("```") or article.endswith("```"):
        issues.append(
            "contains code-block wrapper"
        )

    # --------------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------------

    return (
        len(issues) == 0,
        issues,
    )


# ======================================================================
# SAVE WRITER
# ======================================================================

def save_writer_result(
    writer_id,
    records,
    article,
    validation,
    research_packet=None,
):
    writer = WRITERS[writer_id]

    result = {
        "journalist": writer["name"],
        "role": writer["role"],
        "journalist_id": writer_id,
        "generated_at": now_iso(),
        "model": OLLAMA_MODEL,
        "source": "machina_intelligence_briefs.json",
        "live_web_research": research_packet or [],
        "records_considered": len(records),
        "selected_records": [
            compact_record(r)
            for r in records
        ],
        "article": {
            "body": article,
            "source_record_ids": [
                r.get("record_id")
                for r in records
            ],
            "format": writer["format"],
        },
        "persona_validation": {
            "status": (
                "PASS"
                if validation[0]
                else "FAIL"
            ),
            "issues": validation[1],
        },
    }

    live_file = (
        OUTPUT_DIR
        / f"{writer_id}.json"
    )

    history_file = (
        HISTORY_DIR
        / writer_id
        / f"{timestamp()}.json"
    )

    write_json(
        live_file,
        result,
    )

    write_json(
        history_file,
        result,
    )

    print(
        f"  SAVED: {live_file}"
    )

    print(
        f"  ARCHIVED: {history_file}"
    )

    return result


# ======================================================================
# MAREN — VERIFICATION
# ======================================================================

def persist_maren_result(writer_result):
    """
    Persist the final article and Maren audit without overwriting
    the original pre-Maren history snapshot.
    """
    writer_id = writer_result["journalist_id"]

    live_file = OUTPUT_DIR / f"{writer_id}.json"
    audit_file = (
        HISTORY_DIR
        / writer_id
        / f"{timestamp()}_maren.json"
    )

    # Update the current result, including the final article and audit.
    write_json(live_file, writer_result)

    # Preserve the original history file by writing a separate snapshot.
    write_json(audit_file, writer_result)

    print(f"    SAVED FINAL RESULT: {live_file}")
    print(f"    SAVED MAREN AUDIT: {audit_file}")

    return {
        "live_file": str(live_file),
        "audit_file": str(audit_file),
    }


def maren_prompt(writer_result):
    """
    Lightweight verification gate.

    Maren does not rewrite the article.
    Maren checks whether the journalist stayed on the assigned story,
    used the supplied research, and avoided obvious fabrication.
    """

    selected_records = writer_result.get(
        "selected_records",
        [],
    )

    assigned = (
        selected_records[0]
        if selected_records
        else {}
    )

    assigned_title = clean_title(
        assigned.get("title")
        or assigned.get("name")
        or assigned.get("headline")
        or ""
    )

    assigned_record_id = str(
        assigned.get("record_id")
        or ""
    )

    article = writer_result.get(
        "article",
        {},
    )

    article_title = normalise_text(
        article.get("title")
        or ""
    )

    article_body = normalise_text(
        article.get("body")
        or article.get("content")
        or ""
    )

    research = writer_result.get(
        "live_web_research",
        [],
    )

    compact_research = []

    for item in research[:5]:
        compact_research.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", ""),
                "page_text": item.get(
                    "page_text",
                    "",
                )[:5000],
            }
        )

    payload = {
        "journalist": writer_result.get(
            "journalist",
            "",
        ),
        "journalist_id": writer_result.get(
            "journalist_id",
            "",
        ),
        "assigned_record_id": assigned_record_id,
        "assigned_story_title": assigned_title,
        "article_title": article_title,
        "article_body": article_body,
        "live_web_research": compact_research,
    }

    return f"""
You are MAREN, Machina Daily's lightweight verification editor.

Your job is NOT to rewrite the article.

Your job is to decide whether this journalist wrote about the
CORRECT ASSIGNED STORY and whether the article contains obvious
unsupported invention.

ASSIGNED STORY:
{assigned_title}

ASSIGNED RECORD ID:
{assigned_record_id}

JOURNALIST ARTICLE:
{json.dumps(payload, ensure_ascii=False, indent=2)}

VERIFICATION RULES — EVIDENCE FIRST:

1. Use the supplied intelligence record and live research as the evidence
   available for this review. Do not assume claims are true because they
   sound plausible.

2. Check the article's central factual claims against the actual evidence.
   A source title, URL, query, or company name alone does not prove a claim.
   The source content must substantively support it.

3. Apply strict scrutiny to acquisitions, partnerships, contracts, launches,
   announcements, funding, revenue, prices, financial results, dates, named
   people, quotations, performance figures and company relationships.

4. Specific transactions, deal amounts, closing dates, named counterparties
   and announcements require direct supporting evidence. Do not infer a deal
   from a broad company story or a similar-sounding company name.

5. Distinguish reported facts from analysis. Clearly signalled interpretation
   may be acceptable without direct proof of every inference, provided it
   does not rely on invented events or misrepresented facts.

6. If a central factual claim is not supported by the supplied evidence,
   FAIL the article and identify the unsupported claim in "issues". Lack of
   evidence does not prove a claim false; it means the claim is unverified.

7. If live research is empty or inconclusive, inspect the selected
   intelligence record. PASS only when the central factual claims are
   supported by that record or other supplied evidence.

8. Check whether each source actually supports the claim attributed to it.
   Irrelevant pages, unrelated results and repeated copies of one assertion
   are not corroboration.

PASS only when:
- the article concerns the correct assigned story;
- its headline and body match that story;
- its central factual claims are supported by supplied evidence;
- no material invented event, transaction, amount, date, quotation,
  organisation, person, capability or relationship is presented as fact;
- analysis is distinguishable from reported fact.

FAIL when:
- the article is about the wrong story;
- a central factual claim is unsupported by supplied evidence;
- a deal, acquisition, announcement, amount or date is asserted without
  evidence that substantively supports it;
- the article misrepresents its sources;
- material factual details appear invented;
- the article is mostly generic filler unrelated to the assigned story.

Do NOT fail merely because:
- the intelligence record is sparse;
- live research is limited;
- the article is concise;
- the journalist uses cautious language;
- clearly signalled analysis is not itself a reported fact.

Never treat missing search results as proof that an event did not happen.
Fail an unverified central claim because it lacks the evidence required
for publication, not because its falsity has been established.
Return ONLY valid JSON:

{{
  "status": "PASS" or "FAIL",
  "issues": [],
  "verified_claims": []
}}

Do NOT use PASS as the default.
PASS requires affirmative evidence supporting the central factual claims.
If a material central claim remains unverified after reviewing all supplied
evidence, use FAIL and identify the specific unsupported claim.
Do not fail solely because minor, non-material details remain uncertain.

Do not rewrite the article.
""".strip()

def verify_with_maren(writer_result):
    """Fail closed when Maren returns invalid verification data."""
    prompt = maren_prompt(writer_result)
    response = ollama_generate(prompt)
    parsed = extract_json(response)

    if not isinstance(parsed, dict):
        return {
            "status": "FAIL",
            "issues": ["Maren returned malformed verification JSON; verification failed closed."],
            "verified_claims": [],
        }

    status = parsed.get("status")
    if not isinstance(status, str) or status.strip().upper() not in {"PASS", "FAIL"}:
        return {
            "status": "FAIL",
            "issues": ["Maren returned a missing or invalid status; verification failed closed."],
            "verified_claims": [],
        }

    issues = parsed.get("issues")
    claims = parsed.get("verified_claims")

    if not isinstance(issues, list) or not isinstance(claims, list):
        return {
            "status": "FAIL",
            "issues": ["Maren returned malformed verification fields; verification failed closed."],
            "verified_claims": [],
        }

    return {
        "status": status.strip().upper(),
        "issues": issues,
        "verified_claims": claims,
    }

def yuki_prompt(verified_results):
    """
    Yuki ranks the exact verified journalist articles.

    Yuki does not rewrite, replace or generate article subjects.
    """

    stories = []

    for index, result in enumerate(
        verified_results,
        start=1,
    ):
        selected_records = result.get(
            "selected_records",
            [],
        )

        assigned = (
            selected_records[0]
            if selected_records
            else {}
        )

        stories.append(
            {
                "index": index,
                "journalist_id": result.get(
                    "journalist_id",
                    "",
                ),
                "journalist": result.get(
                    "journalist",
                    "",
                ),
                "assigned_record_id": str(
                    assigned.get(
                        "record_id",
                        "",
                    )
                ),
                "assigned_story_title": clean_title(
                    assigned.get("title")
                    or assigned.get("name")
                    or assigned.get("headline")
                    or ""
                ),
                "article": result.get(
                    "article",
                    {},
                ),
            }
        )

    return f"""
You are YUKI TANAKA, Machina Daily's final desk editor.

You are ranking already-written and already-verified specialist
articles.

You MUST NOT rewrite them.
You MUST NOT invent new stories.
You MUST NOT substitute one story for another.

Choose up to five articles from the supplied list.

Rank them according to:
1. journalistic quality;
2. evidence and specificity;
3. genuine reader interest;
4. distinctiveness;
5. importance appropriate to the evidence.

The assigned story title and record ID are IDENTITIES.

They must be preserved exactly.

SOURCE ARTICLES:

{json.dumps(stories, ensure_ascii=False, indent=2)}

Return ONLY valid JSON:

{{
  "top_five": [
    {{
      "rank": 1,
      "journalist_id": "exact supplied journalist_id",
      "assigned_record_id": "exact supplied assigned_record_id",
      "assigned_story_title": "exact supplied assigned_story_title",
      "reason": "short editorial reason"
    }}
  ]
}}

Rules:
- Only select journalist_id values supplied above.
- Never invent a journalist_id.
- Never invent a record_id.
- Never change an assigned story title.
- Never combine two stories.
- Never select an article that is not in the supplied list.
- Maximum five selections.
""".strip()

def run_yuki(verified_results):
    """
    Run Yuki and resolve her selections back to the exact verified
    journalist result.

    The returned top_five contains identity metadata only.
    The original article remains in verified_results.
    """

    if not verified_results:
        return {
            "status": "NO_VERIFIED_STORIES",
            "top_five": [],
        }

    prompt = yuki_prompt(
        verified_results
    )

    try:
        response = ollama_generate(
            prompt
        )
    except Exception as exc:
        print(f"  Yuki AI timed out or failed: {exc}")
        print("  Falling back to verified editorial order.")
        response = '{"top_five": []}'

    parsed = extract_json(
        response
    )

    if not isinstance(parsed, dict):
        return {
            "status": "FAIL",
            "top_five": [],
            "error": "Yuki returned invalid JSON.",
        }

    requested = parsed.get(
        "top_five",
        [],
    )

    if not isinstance(
        requested,
        list,
    ):
        requested = []

    lookup = {}

    for result in verified_results:
        selected_records = result.get(
            "selected_records",
            [],
        )

        assigned = (
            selected_records[0]
            if selected_records
            else {}
        )

        journalist_id = result.get(
            "journalist_id",
            "",
        )

        record_id = str(
            assigned.get(
                "record_id",
                "",
            )
        )

        lookup[
            (
                journalist_id,
                record_id,
            )
        ] = result

    top_five = []

    for item in requested:
        journalist_id = str(
            item.get(
                "journalist_id",
                "",
            )
        )

        record_id = str(
            item.get(
                "assigned_record_id",
                "",
            )
        )

        result = lookup.get(
            (
                journalist_id,
                record_id,
            )
        )

        if result is None:
            continue

        assigned = result.get(
            "selected_records",
            [{}],
        )[0]

        top_five.append(
            {
                "rank": len(top_five) + 1,
                "journalist_id": journalist_id,
                "journalist": result.get(
                    "journalist",
                    "",
                ),
                "assigned_record_id": record_id,
                "assigned_story_title": clean_title(
                    assigned.get("title")
                    or assigned.get("name")
                    or assigned.get("headline")
                    or ""
                ),
                "article_title": result.get(
                    "article",
                    {},
                ).get(
                    "title",
                    "",
                ),
                "reason": item.get(
                    "reason",
                    "",
                ),
            }
        )

        if len(top_five) >= 5:
            break

    # If Yuki produced unusable selections, retain the verified
    # editorial order rather than losing the entire briefing.
    if not top_five:
        for result in verified_results[:5]:
            selected_records = result.get(
                "selected_records",
                [],
            )

            assigned = (
                selected_records[0]
                if selected_records
                else {}
            )

            top_five.append(
                {
                    "rank": len(top_five) + 1,
                    "journalist_id": result.get(
                        "journalist_id",
                        "",
                    ),
                    "journalist": result.get(
                        "journalist",
                        "",
                    ),
                    "assigned_record_id": str(
                        assigned.get(
                            "record_id",
                            "",
                        )
                    ),
                    "assigned_story_title": clean_title(
                        assigned.get("title")
                        or assigned.get("name")
                        or assigned.get("headline")
                        or ""
                    ),
                    "article_title": result.get(
                        "article",
                        {},
                    ).get(
                        "title",
                        "",
                    ),
                    "reason": "Verified fallback ranking",
                }
            )

    return {
        "status": "PASS",
        "top_five": top_five,
    }

def dana_prompt(top_story):
    """
    Dana creates distribution headlines from the exact selected article.

    Dana is not an editorial writer.
    """

    selected_records = top_story.get(
        "selected_records",
        [],
    )

    assigned = (
        selected_records[0]
        if selected_records
        else {}
    )

    assigned_title = clean_title(
        assigned.get("title")
        or assigned.get("name")
        or assigned.get("headline")
        or ""
    )

    assigned_record_id = str(
        assigned.get(
            "record_id",
            "",
        )
    )

    article = top_story.get(
        "article",
        {},
    )

    article_title = normalise_text(
        article.get(
            "title",
            "",
        )
    )

    article_body = normalise_text(
        article.get(
            "body",
            "",
        )
    )

    return f"""
You are DANA OKAFOR, Machina Daily's distribution editor.

Create three short push/newsletter headline options for the EXACT
article supplied below.

ASSIGNED STORY:
{assigned_title}

ASSIGNED RECORD ID:
{assigned_record_id}

ARTICLE TITLE:
{article_title}

ARTICLE BODY:
{article_body}

NON-NEGOTIABLE RULES:

The push options MUST describe the assigned story above.

Do NOT introduce another company.
Do NOT introduce another research paper.
Do NOT introduce another product.
Do NOT introduce another technology.
Do NOT use facts from your general knowledge.
Do NOT substitute a familiar story.
Do NOT mention IBM, quantum computing, or any other subject unless
it appears in the supplied article.

Each option must be directly understandable from the supplied article.

Return ONLY valid JSON:

{{
  "options": [
    "headline option 1",
    "headline option 2",
    "headline option 3"
  ]
}}

No commentary.
""".strip()

def run_dana(top_story):
    """
    Generate distribution options from the exact selected article.
    """

    if not top_story:
        return {
            "status": "NO_TOP_STORY",
            "options": [],
        }

    prompt = dana_prompt(
        top_story
    )

    response = ollama_generate(
        prompt
    )

    parsed = extract_json(
        response
    )

    if not isinstance(parsed, dict):
        return {
            "status": "FAIL",
            "options": [],
            "error": "Dana returned invalid JSON.",
        }

    options = parsed.get(
        "options",
        [],
    )

    if not isinstance(
        options,
        list,
    ):
        options = []

    cleaned = []

    for option in options:
        option = normalise_text(
            option
        )

        if not option:
            continue

        cleaned.append(
            option
        )

        if len(cleaned) >= 3:
            break

    if not cleaned:
        article = top_story.get(
            "article",
            {},
        )

        fallback_title = normalise_text(
            article.get(
                "title",
                "",
            )
        )

        if fallback_title:
            cleaned = [
                fallback_title,
                f"Machina Daily: {fallback_title}",
                f"What happened: {fallback_title}",
            ]

    return {
        "status": "PASS",
        "options": cleaned[:3],
    }

def build_master(writer_results, maren_results, yuki, dana, candidate_pool):
    """Assemble the final newsroom output without changing writer results."""

    pool = candidate_pool if isinstance(candidate_pool, dict) else {}

    routing = {}
    for writer_id, records in pool.items():
        if not isinstance(records, list):
            records = []

        routing[writer_id] = [
            record.get("record_id") or record.get("id")
            for record in records
            if isinstance(record, dict)
            and (record.get("record_id") or record.get("id"))
        ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": OLLAMA_MODEL,
        "source": "machina_intelligence_briefs.json",
        "architecture": {
            "selector": "global candidate pool",
            "writers": list(WRITER_IDS),
            "verification": "Maren",
            "ranking": "Yuki Tanaka",
            "distribution": "Dana Okafor",
        },
        "results": writer_results,
        "maren_verification": maren_results,
        "yuki": yuki,
        "dana": dana,
        "routing": routing,
        "candidate_counts": {
            writer_id: len(records) if isinstance(records, list) else 0
            for writer_id, records in pool.items()
        },
    }


def verify_with_maren_and_repair(writer_result):
    """Allow one factual repair and one Maren recheck; fail closed."""
    article = writer_result.get("article")
    if not isinstance(article, dict):
        article = {}
        writer_result["article"] = article

    original_body = str(
        article.get("body") or article.get("content") or ""
    )

    def make_fail(message):
        return {
            "status": "FAIL",
            "issues": [str(message)],
            "verified_claims": [],
        }

    try:
        initial = verify_with_maren(writer_result)
    except Exception as exc:
        initial = make_fail(f"Maren error: {exc}")

    if not isinstance(initial, dict):
        initial = make_fail("Maren returned an invalid result.")

    if initial.get("status") == "PASS":
        writer_result["maren_repair"] = {
            "attempted": False,
            "original_article": original_body,
            "corrected_article": None,
            "initial_verification": initial,
            "repair_validation": None,
            "final_verification": initial,
        }
        return initial

    writer_id = writer_result.get("journalist_id", "")
    writer = WRITERS.get(writer_id, {})
    selected = writer_result.get("selected_records", [])
    research = writer_result.get("live_web_research", [])
    issues = initial.get("issues", [])
    if not isinstance(issues, list):
        issues = [str(issues)]

    repair_prompt = f"""
You are {writer.get("name", writer_result.get("journalist", "the journalist"))},
writing for Machina Daily.

Maren rejected your article. You have exactly ONE correction attempt.
Address each specific objection below.

SPECIALIST INSTRUCTIONS:
{writer.get("instruction", "")}

MAREN'S OBJECTIONS:
{chr(10).join("- " + str(issue) for issue in issues)}

ASSIGNED INTELLIGENCE RECORDS:
{json.dumps(selected, ensure_ascii=False, indent=2)}

SUPPLIED LIVE RESEARCH:
{json.dumps(research, ensure_ascii=False, indent=2)}

ORIGINAL ARTICLE:
{original_body}

Correct or remove unsupported claims. Do not invent facts, sources, quotes,
figures, dates, or relationships. Preserve the assigned story and specialist
perspective. Follow the journalist's normal instructions and word ceiling.
Return only the complete corrected article.
"""

    corrected = ""
    repair_validation = {"status": "FAIL", "issues": []}

    try:
        corrected = str(ollama_generate(repair_prompt) or "").strip()
    except Exception as exc:
        repair_validation["issues"].append(
            f"Correction generation failed: {exc}"
        )

    final = make_fail("Correction was not produced or did not pass validation.")

    if corrected:
        try:
            validation = validate_writer_output(
                writer_id, corrected, selected
            )
            valid = (
                isinstance(validation, (tuple, list))
                and len(validation) >= 2
                and bool(validation[0])
            )
            validation_issues = (
                list(validation[1])
                if isinstance(validation, (tuple, list))
                and len(validation) >= 2
                else ["Validator returned an invalid result."]
            )
        except Exception as exc:
            valid = False
            validation_issues = [f"Writer validation error: {exc}"]

        repair_validation = {
            "status": "PASS" if valid else "FAIL",
            "issues": validation_issues,
        }

        if valid:
            # Maren must see the corrected body, not the original.
            article["body"] = corrected
            try:
                final = verify_with_maren(writer_result)
                if not isinstance(final, dict):
                    final = make_fail(
                        "Maren returned an invalid result on recheck."
                    )
            except Exception as exc:
                final = make_fail(f"Maren recheck error: {exc}")

            if final.get("status") != "PASS":
                final["status"] = "FAIL"
                final.setdefault("issues", [])
                final.setdefault("verified_claims", [])
        else:
            final = make_fail(
                "Corrected article failed writer validation: "
                + "; ".join(str(x) for x in validation_issues)
            )

    writer_result["maren_repair"] = {
        "attempted": True,
        "original_article": original_body,
        "corrected_article": corrected or None,
        "initial_verification": initial,
        "repair_validation": repair_validation,
        "final_verification": final,
    }
    return final


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    HISTORY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 70)
    print(
        "MACHINA DAILY — DAILY BRIEFING EDITORIAL ENGINE"
    )
    print("=" * 70)
    print()
    print(
        "Local intelligence → selector → six writers → Maren → Yuki → Dana."
    )
    print()
    print("No OpenAI.")
    print("Controlled DDGS desk research enabled.")
    print(
        f"Ollama model: {OLLAMA_MODEL}"
    )
    print()

    records = load_intelligence()

    if not records:
        raise RuntimeError(
            "No intelligence records found."
        )

    previous = load_previous_coverage()

    candidate_pool, unrouted, global_selected = select_global_stories(
        records,
        previous,
    )

    print(
        f"Intelligence records loaded: {len(records)}"
    )

    print(
        f"Previous coverage files: {len(previous)}"
    )

    print()
    print("SELECTOR — DAILY BRIEFING CANDIDATE POOL")
    print("-" * 70)

    for writer_id in WRITER_IDS:
        print(
            f"  {WRITERS[writer_id]['name']}: "
            f"{len(candidate_pool.get(writer_id, []))} candidates"
        )

    print(
        f"  Unrouted: {len(unrouted)} records"
    )

    print()

    writer_results = []
    maren_results = []

    for writer_id in WRITER_IDS:
        writer = WRITERS[writer_id]

        print("=" * 70)
        print(
            f"{writer['name'].upper()} — {writer['role'].upper()}"
        )
        print("=" * 70)

        candidates = candidate_pool.get(
            writer_id,
            []
        )

        selected = select_for_writer(
            candidates
        )

        if not selected:
            print(
                "  No records routed to this desk."
            )
            continue

        print(
            f"  Selector selected {len(selected)} records"
        )

        for index, record in enumerate(
            selected,
            start=1,
        ):
            print(
                f"    {index}. "
                f"{clean_title(record.get('title'))}"
            )

        print()
        print(
            "  LIVE WEB RESEARCH — "
            f"{WRITERS[writer_id]['name']}"
        )
        print(
            "  Running controlled desk-specific searches..."
        )

        web_research = run_web_research(
            writer_id,
            selected,
        )

        print(
            f"  Live research results: {len(web_research)}"
        )

        for index, item in enumerate(
            web_research,
            start=1,
        ):
            print(
                f"    WEB {index}. "
                f"{item.get('title', '')[:110]}"
            )
            print(
                f"           {item.get('url', '')}"
            )

        print()
        print(
            "  Writing with desk persona..."
        )

        prompt = writer_prompt(
            writer_id,
            selected,
            previous,
            web_research,
        )

        if writer_id == "callum_reyes":
            debug_prompt_path = OUTPUT_DIR / "debug_callum_prompt.txt"
            debug_prompt_path.write_text(
                prompt,
                encoding="utf-8",
            )
            print(
                f"  DEBUG PROMPT SAVED: {debug_prompt_path}"
            )

        try:
            article = openai_generate(
                prompt
            )
        except Exception as exc:
            print(
                f"  WRITER ERROR: {exc}"
            )
            continue

        validation = validate_writer_output(
            writer_id,
            article,
            selected,
        )

        print(
            "  Persona validation: "
            + (
                "PASS"
                if validation[0]
                else "FAIL"
            )
        )

        if not validation[0]:
            for issue in validation[1]:
                print(
                    f"    - {issue}"
                )

            print("  Requesting one focused correction attempt...")

            repair_prompt = f"""
You are {WRITERS[writer_id]["name"]}, writing for Machina Daily.

Your previous article failed deterministic validation.
Fix the listed problems while preserving the assigned story,
specialist role, and supported facts.

SPECIALIST INSTRUCTIONS:
{WRITERS[writer_id]["instruction"]}

VALIDATION PROBLEMS:
{chr(10).join("- " + issue for issue in validation[1])}

ASSIGNED STORY AND RESEARCH:
{selected}

PREVIOUS ARTICLE:
{article}

Return only the corrected article.
Follow your own specialist word limit.
Do not invent facts or present unverified information as confirmed.
"""

            try:
                repaired_article = openai_generate(repair_prompt)
                repaired_validation = validate_writer_output(
                    writer_id,
                    repaired_article,
                    selected,
                )
            except Exception as exc:
                print(f"  Correction attempt failed: {exc}")
                continue

            if not repaired_validation[0]:
                print("  Correction still failed validation:")
                for issue in repaired_validation[1]:
                    print(f"    - {issue}")
                print("  Bulletin rejected before Maren.")
                continue

            article = repaired_article
            validation = repaired_validation
            print("  Correction passed persona validation.")

        result = save_writer_result(
            writer_id,
            selected,
            article,
            validation,
            web_research,
        )

        writer_results.append(
            result
        )

    # --------------------------------------------------------------
    # MAREN
    # --------------------------------------------------------------

    print()
    print("=" * 70)
    print("MAREN — VERIFICATION GATE")
    print("=" * 70)

    verified_results = []

    for result in writer_results:
        print(
            f"  Verifying {result['journalist']}..."
        )

        verification = verify_with_maren_and_repair(result)
        result["maren_verification"] = verification

        persist_maren_result(result)

        repair = result.get("maren_repair", {})
        maren_results.append(
            {
                "journalist_id": result["journalist_id"],
                "status": verification.get("status", "FAIL"),
                "issues": verification.get("issues", []),
                "verified_claims": verification.get("verified_claims", []),
                "initial_status": repair.get(
                    "initial_verification", {}
                ).get("status", verification.get("status", "FAIL")),
                "repair_attempted": repair.get("attempted", False),
                "repair_validation_status": (repair.get("repair_validation") or {}).get("status"),
            }
        )

        print(
            f"    Maren: {verification.get('status', 'FAIL')}"
        )

        if repair.get("attempted"):
            print(
                "    Correction validation: "
                + str(
                    repair.get("repair_validation", {}).get(
                        "status", "FAIL"
                    )
                )
                + " | Final Maren decision: "
                + str(verification.get("status", "FAIL"))
            )

        if verification.get("status") == "PASS":
            verified_results.append(result)
            record_successful_story_memory(result)

    # SAVE CHECKPOINT BEFORE YUKI
    # Preserve completed writer and Maren work if ranking times out.
    checkpoint_master = build_master(
        writer_results,
        maren_results,
        {
            "status": "PENDING",
            "top_five": [],
            "note": "Ranking has not completed yet.",
        },
        {
            "status": "PENDING",
            "options": [],
            "note": "Distribution has not completed yet.",
        },
        candidate_pool,
    )
    write_json(MASTER_FILE, checkpoint_master)
    print(f"  CHECKPOINT SAVED before Yuki: {MASTER_FILE}")

    # YUKI
    # --------------------------------------------------------------

    print()
    print("=" * 70)
    print("YUKI TANAKA — DESK EDITOR")
    print("=" * 70)

    print(
        f"  Ranking {len(verified_results)} verified bulletins..."
    )

    yuki = run_yuki(
        verified_results
    )

    print(
        f"  Top stories selected: "
        f"{len(yuki.get('top_five', []))}"
    )

    for item in yuki.get(
        "top_five",
        [],
    ):
        print(
            f"    #{item['rank']} "
            f"{item['journalist_id']}"
        )

    # --------------------------------------------------------------
    # DANA
    # --------------------------------------------------------------

    print()
    print("=" * 70)
    print("DANA OKAFOR — DISTRIBUTION / PUSH")
    print("=" * 70)

    dana = {
        "status": "NO_TOP_STORY",
        "options": [],
    }

    top_story = None

    if yuki.get("top_five"):
        top_id = yuki[
            "top_five"
        ][0]["journalist_id"]

        top_story = next(
            (
                r
                for r in verified_results
                if r["journalist_id"]
                == top_id
            ),
            None,
        )

    if top_story:
        print(
            f"  Generating push options for: "
            f"{top_story['journalist']}"
        )

        try:
            dana = run_dana(
                top_story
            )
    
        except Exception as exc:
            dana = {
                "status": "FAIL",
                "options": [],
                "error": str(exc),
            }

    else:
        print(
            "  No verified top story available."
        )

    if dana.get("options"):
        for index, option in enumerate(
            dana["options"],
            start=1,
        ):
            print(
                f"    {index}. {option}"
            )

    # --------------------------------------------------------------
    # MASTER
    # --------------------------------------------------------------

    master = build_master(
        writer_results,
        maren_results,
        yuki,
        dana,
        candidate_pool,
    )

    write_json(
        MASTER_FILE,
        master,
    )

    print()
    print("=" * 70)
    print(
        "DAILY BRIEFING EDITORIAL ENGINE COMPLETE"
    )
    print("=" * 70)
    print(
        f"Writer bulletins: {len(writer_results)}"
    )
    print(
        f"Maren PASS: "
        f"{len(verified_results)}"
    )
    print(
        f"Yuki top five: "
        f"{len(yuki.get('top_five', []))}"
    )
    print(
        f"Dana push options: "
        f"{len(dana.get('options', []))}"
    )
    print(
        f"Results: {MASTER_FILE}"
    )
    print(
        f"History: {HISTORY_DIR}"
    )
    print()


if __name__ == "__main__":
    main()


































