"""Game content for Powerhouse: pathways, upgrades, enzymes, cosmetics,
achievements, quests and level titles.

Everything here is plain data so it can be unit-tested without Anki.
Medical facts are written to be accurate at a Step 1 level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Rarity
# ---------------------------------------------------------------------------

RARITIES = ("common", "rare", "epic", "legendary")
RARITY_WEIGHTS = {"common": 70.0, "rare": 22.0, "epic": 7.3, "legendary": 0.7}
RARITY_WEIGHTS_RAB = {"common": 64.0, "rare": 25.0, "epic": 9.9, "legendary": 1.1}  # with the Rab GTPase upgrade

# ---------------------------------------------------------------------------
# Pathways (the "buildings"). Each one adds ATP per card answered.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pathway:
    id: str
    name: str
    base_cost: float
    base_yield: float  # ATP added per card, per copy owned
    blurb: str


PATHWAYS: list[Pathway] = [
    Pathway("glycolysis", "Glycolysis", 15, 0.1,
            "Glucose → 2 pyruvate for a net 2 ATP. PFK-1 sets the pace."),
    Pathway("pdh", "Pyruvate dehydrogenase", 270, 0.6,
            "Links glycolysis to the Krebs cycle. Needs B1, lipoic acid, B2, B3 and B5."),
    Pathway("krebs", "Krebs cycle", 5_000, 4,
            "Each turn makes 3 NADH, 1 FADH₂ and 1 GTP. Isocitrate dehydrogenase is rate-limiting."),
    Pathway("etc", "Electron transport chain", 90_000, 25,
            "Complexes I, III and IV pump protons. Cyanide and CO block Complex IV."),
    Pathway("synthase", "ATP synthase", 1_600_000, 160,
            "Complex V spins on the proton gradient. Oligomycin jams the rotor."),
    Pathway("betaox", "β-oxidation", 28_000_000, 1_000,
            "Long-chain fatty acids enter through the carnitine shuttle. Malonyl-CoA blocks CAT-1."),
    Pathway("ketones", "Ketone bodies", 500_000_000, 6_300,
            "The liver makes them with HMG-CoA synthase; brain, heart and muscle burn them. "
            "The brain's main backup fuel in starvation."),
    Pathway("creatine", "Creatine phosphate", 9_000_000_000, 40_000,
            "The fastest ATP refill: creatine kinase hands phosphate straight to ADP. "
            "Runs dry in about ten seconds flat out."),
    # id kept as "brownfat" so existing saves carry over
    Pathway("brownfat", "Slow-twitch fibers", 70_000_000_000, 250_000,
            "Type I muscle: red with myoglobin and packed with mitochondria. One slow red ox."),
    Pathway("biogenesis", "Mitochondrial biogenesis", 700_000_000_000, 1_600_000,
            "PGC-1α tells the cell to build more of you."),
]

PATHWAY_BY_ID = {p.id: p for p in PATHWAYS}
COST_GROWTH = 1.15

# ---------------------------------------------------------------------------
# Upgrades
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Upgrade:
    id: str
    name: str
    blurb: str
    cost: float
    kind: str  # "pathway" | "habit" | "vesicle" | "flow"
    # pathway upgrades
    pathway: Optional[str] = None
    owned_needed: int = 0
    factor: float = 2.0
    # habit upgrades: unlocked after this many answers since install
    answers_needed: int = 0


# Thresholds (copies owned) and cost multipliers relative to the pathway's base cost.
PATHWAY_UPGRADE_TIERS = [(10, 12), (25, 160), (50, 9_000), (100, 1_500_000)]

_PATHWAY_UPGRADE_NAMES: dict[str, list[tuple[str, str]]] = {
    "glycolysis": [
        ("Fructose-2,6-bisphosphate", "Insulin's favorite PFK-1 activator."),
        ("Hexokinase hustle", "Trap glucose in the cell before it escapes."),
        ("Feed-forward", "Fructose-1,6-bisphosphate revs up pyruvate kinase."),
        ("Cori cycle", "Muscle lactate goes back to the liver to be recycled."),
    ],
    "pdh": [
        ("Thiamine top-up", "B1 keeps PDH running. Alcohol use drains it."),
        ("Lipoic acid", "The swinging arm that carries acetyl groups."),
        ("PDH phosphatase", "Dephosphorylation switches PDH on."),
        ("Arsenic-free diet", "Arsenite binds lipoic acid. Avoid it."),
    ],
    "krebs": [
        ("ADP surplus", "Isocitrate dehydrogenase speeds up when ADP is high."),
        ("Calcium spark", "Ca²⁺ activates key Krebs enzymes in working muscle."),
        ("Oxaloacetate refill", "Pyruvate carboxylase keeps the cycle topped up."),
        ("Succinyl-CoA swap", "Substrate-level phosphorylation makes a GTP."),
    ],
    "etc": [
        ("Coenzyme Q", "The mobile carrier between Complexes I/II and III."),
        ("Cytochrome c", "Shuttles electrons from Complex III to IV."),
        ("Cristae folding", "More inner-membrane folds, more room for complexes."),
        ("Steep gradient", "About 4 protons per ATP in all: 2.7 turn the rotor, 1 brings in ADP and phosphate."),
    ],
    "synthase": [
        ("Rotor polish", "Three ATP per full turn of the γ-subunit."),
        ("c8 ring", "Mammals' c-ring has just 8 subunits: about 2.7 protons per ATP, cheaper than yeast or bacteria."),
        ("Coupled tightly", "No leaks: every proton earns its keep."),
        ("Oligomycin-free zone", "Keep the Fo channel open."),
    ],
    "betaox": [
        ("Carnitine supplement", "Fatty acids ride carnitine into the matrix."),
        ("MCAD on duty", "Medium-chain acyl-CoA dehydrogenase, working as intended."),
        ("Glucagon signal", "Fasting flips the switch toward fat burning."),
        ("Peroxisome assist", "Very-long-chain fats get trimmed in peroxisomes first."),
    ],
    "ketones": [
        ("Overnight fast", "Low insulin, high glucagon, ketones on."),
        ("β-hydroxybutyrate", "The ketone body that urine dipsticks miss."),
        ("Acetoacetate", "The ketone body the dipstick does catch."),
        ("No thiophorase", "The liver can't burn its own ketones, so it exports every one."),
    ],
    "creatine": [
        ("Creatine kinase", "Phosphocreatine + ADP → creatine + ATP."),
        ("Phosphagen burst", "Instant energy for the first seconds of a sprint."),
        ("Creatine loading", "Supplements top up phosphocreatine stores."),
        ("Mitochondrial creatine kinase", "Sits in Mito's intermembrane space, recharging phosphocreatine with fresh ATP."),
    ],
    "brownfat": [  # slow-twitch fibers
        ("Myoglobin", "Stores O₂ in red fibers. Its curve sits left of hemoglobin's."),
        ("Capillary bed", "Dense capillaries keep the O₂ coming."),
        ("Postural muscles", "The soleus is mostly type I: it holds you up all day."),
        ("Fatigue resistance", "Oxidative fibers keep going long after fast ones tire."),
    ],
    "biogenesis": [
        ("Endurance training", "Aerobic exercise makes more mitochondria."),
        ("PGC-1α boost", "The master regulator, fully awake."),
        ("Fusion & fission", "Mitochondria constantly merge and split."),
        ("Maternal inheritance", "Every mitochondrion you have came from mom."),
    ],
}


def _build_pathway_upgrades() -> list[Upgrade]:
    out: list[Upgrade] = []
    for p in PATHWAYS:
        names = _PATHWAY_UPGRADE_NAMES[p.id]
        for (owned, mult), (name, blurb) in zip(PATHWAY_UPGRADE_TIERS, names):
            out.append(Upgrade(
                id=f"{p.id}_{owned}",
                name=name,
                blurb=f"{blurb} {p.name} output ×2.",
                cost=p.base_cost * mult,
                kind="pathway",
                pathway=p.id,
                owned_needed=owned,
                factor=2.0,
            ))
    return out


HABIT_UPGRADES: list[Upgrade] = [
    Upgrade("coffee", "Coffee", "Adenosine receptor antagonist. You know what you did. All ATP ×1.1.",
            300, "habit", factor=1.10, answers_needed=150),
    Upgrade("water", "Water bottle", "Hydrated neurons fire better. All ATP ×1.1.",
            2_500, "habit", factor=1.10, answers_needed=500),
    Upgrade("headphones", "Noise-cancelling headphones", "The library is louder than it looks. All ATP ×1.15.",
            75_000, "habit", factor=1.15, answers_needed=1_500),
    Upgrade("pomodoro", "Pomodoro timer", "25 on, 5 off: flow now waits out a 5-minute break. All ATP ×1.2.",
            600_000, "habit", factor=1.20, answers_needed=3_000),
    Upgrade("desk", "Standing desk", "Your posture called. All ATP ×1.25.",
            6_000_000, "habit", factor=1.25, answers_needed=6_000),
    Upgrade("sleep", "Eight hours of sleep", "Memories consolidate while you sleep. Seriously, go to bed. All ATP ×1.5.",
            50_000_000, "habit", factor=1.50, answers_needed=10_000),
    Upgrade("group", "Study group", "Explaining it out loud is retrieval practice too. All ATP ×1.25.",
            1_500_000_000, "habit", factor=1.25, answers_needed=20_000),
    Upgrade("annotated", "Annotated review book", "Margins full of your own handwriting. All ATP ×1.5.",
            20_000_000_000, "habit", factor=1.50, answers_needed=35_000),
    Upgrade("qbank", "Question bank streak", "Retrieval practice, now with vignettes. All ATP ×1.5.",
            1e11, "habit", factor=1.50, answers_needed=50_000),
    Upgrade("mastery", "Spaced repetition mastery", "You trust the algorithm, and it trusts you. All ATP ×2.",
            6e11, "habit", factor=2.0, answers_needed=75_000),
    Upgrade("boards", "Board certified", "All ATP ×2.",
            1.5e12, "habit", factor=2.0, answers_needed=100_000),
    Upgrade("attending", "Attending energy", "Calm, fast, and still learning. All ATP ×2.5.",
            4e12, "habit", factor=2.5, answers_needed=150_000),
]

VESICLE_UPGRADES: list[Upgrade] = [
    Upgrade("clathrin", "Clathrin coat", "Vesicles bud more often: +15% find rate.",
            2_000, "vesicle", factor=1.15, answers_needed=400),
    Upgrade("snare", "SNARE proteins", "Cleaner fusion: ATP from vesicles ×2.",
            150_000, "vesicle", factor=2.0, answers_needed=2_000),
    Upgrade("rab", "Rab GTPase", "Better cargo sorting: rarer vesicles turn up more.",
            25_000_000, "vesicle", factor=1.0, answers_needed=8_000),
    Upgrade("dynamin", "Dynamin pinch", "Faster budding: another +15% find rate.",
            1_500_000_000, "vesicle", factor=1.15, answers_needed=20_000),
]

FLOW_UPGRADES: list[Upgrade] = [
    Upgrade("flow1", "Flow state", "Flow can build to ×1.75 instead of ×1.5.",
            20_000, "flow", factor=1.0, answers_needed=1_000),
    Upgrade("flow2", "Deep work", "Flow can build to ×2.",
            150_000_000, "flow", factor=1.0, answers_needed=12_000),
]

UPGRADES: list[Upgrade] = (
    _build_pathway_upgrades() + HABIT_UPGRADES + VESICLE_UPGRADES + FLOW_UPGRADES
)
UPGRADE_BY_ID = {u.id: u for u in UPGRADES}

# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

FLOW_GAP_MS = 3 * 60 * 1000  # a break longer than this resets flow
FLOW_GAP_POMODORO_MS = 6 * 60 * 1000  # with the Pomodoro timer, a 5-minute break is fine
FLOW_STEP = 0.005  # +0.5% per consecutive answer
FLOW_CAPS = {0: 100, 1: 150, 2: 200}  # steps; ×1.5, ×1.75, ×2.0

# ---------------------------------------------------------------------------
# Vesicles (loot drops)
# ---------------------------------------------------------------------------

VESICLE_BASE_CHANCE = 1 / 45  # per answer that counts
VESICLE_PITY = 100  # guaranteed if this many answers pass without a drop
VESICLE_ATP_CARDS = {  # ATP bundle size, in "cards' worth" of current yield
    "common": (10, 20),
    "rare": (30, 60),
    "epic": (100, 190),
    "legendary": (400, 750),
}
ENZYME_CHANCE = {"common": 0.28, "rare": 0.36, "epic": 0.50, "legendary": 0.85}
# bad-luck protection: after this many duplicate legendary enzymes in a row, the next
# legendary is one you're missing (when your level has reached one you don't have)
LEGENDARY_PITY = 2
COSMETIC_CHANCE = {"common": 0.006, "rare": 0.013, "epic": 0.025, "legendary": 0.08}
FREEZE_CHANCE = {"common": 0.0, "rare": 0.0, "epic": 0.0, "legendary": 0.2}  # streak freezes are mostly earned, 1 per 7 days

# Vesicles bud less often as a big day goes on, so a 2,000-card day doesn't bury you in them:
# (up to this many answers that counted today, drop-rate factor). ATP and XP never taper.
VESICLE_TAPER = ((150, 1.0), (500, 0.5), (1000, 0.25), (None, 0.125))

# ---------------------------------------------------------------------------
# Codex: enzymes you collect from vesicles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Enzyme:
    id: str
    name: str
    set: str
    rarity: str
    fact: str


@dataclass(frozen=True)
class EnzymeSet:
    id: str
    name: str
    unlock_level: int = 1  # enzymes from this set only turn up from this level on...
    unlock_day: int = 0  # ...and once this many days have passed since installing


# One new set per title: Pre-med, MS1, MS2, Step 1 survivor, MS3, MS4. The day minimums
# only matter on very heavy schedules (1,000+ cards a day), where levels come fast.
ENZYME_SETS: list[EnzymeSet] = [
    EnzymeSet("sugar", "Glucose metabolism", 1, 0),
    EnzymeSet("storage", "Glycogen & fat stores", 5, 7),
    EnzymeSet("mito", "The mitochondrion", 10, 21),
    EnzymeSet("lipid", "Lipids & steroids", 15, 35),
    EnzymeSet("nitrogen", "Urea cycle & nucleotides", 20, 56),
    EnzymeSet("amines", "Heme & neurotransmitters", 25, 84),
]
SET_BY_ID = {es.id: es for es in ENZYME_SETS}

ENZYMES: list[Enzyme] = [
    # Glycolysis & gluconeogenesis
    Enzyme("hexokinase", "Hexokinase", "sugar", "common",
           "Most tissues. Low Km, inhibited by its own product, glucose-6-phosphate."),
    Enzyme("glucokinase", "Glucokinase", "sugar", "common",
           "Liver and β-cells. High Km, high capacity, induced by insulin."),
    Enzyme("pyruvate_kinase", "Pyruvate kinase", "sugar", "common",
           "Last step of glycolysis. Deficiency causes hemolytic anemia."),
    Enzyme("pyruvate_carboxylase", "Pyruvate carboxylase", "sugar", "rare",
           "Pyruvate → oxaloacetate in mitochondria. Needs biotin; activated by acetyl-CoA."),
    Enzyme("pepck", "PEP carboxykinase", "sugar", "rare",
           "Oxaloacetate → PEP for gluconeogenesis. Uses GTP."),
    Enzyme("f16bpase", "Fructose-1,6-bisphosphatase", "sugar", "epic",
           "Rate-limiting for gluconeogenesis. Inhibited by AMP and fructose-2,6-bisphosphate."),
    Enzyme("g6pd", "G6PD", "sugar", "epic",
           "Rate-limiting for the HMP shunt. Deficiency → hemolysis with Heinz bodies and bite cells."),
    Enzyme("pfk1", "PFK-1", "sugar", "legendary",
           "Rate-limiting step of glycolysis. Fired up by AMP and fructose-2,6-bisphosphate."),
    # Glycogen & storage
    Enzyme("branching", "Branching enzyme", "storage", "common",
           "Builds α-1,6 branches. Deficiency is Andersen disease (type IV)."),
    Enzyme("debranching", "Debranching enzyme", "storage", "common",
           "Removes α-1,6 branches. Deficiency is Cori disease (type III)."),
    Enzyme("hsl", "Hormone-sensitive lipase", "storage", "common",
           "Frees fatty acids from fat cells when you fast. Insulin shuts it off."),
    Enzyme("myophosphorylase", "Myophosphorylase", "storage", "rare",
           "Muscle glycogen phosphorylase. Missing in McArdle disease (type V): cramps, myoglobinuria."),
    Enzyme("acid_maltase", "Acid α-glucosidase", "storage", "rare",
           "Lysosomal glycogen breakdown. Missing in Pompe disease (type II), which hits the heart."),
    Enzyme("glycogen_synthase", "Glycogen synthase", "storage", "epic",
           "Rate-limiting for glycogen synthesis. Insulin turns it on."),
    Enzyme("g6pase", "Glucose-6-phosphatase", "storage", "epic",
           "Final step of hepatic glucose release. Missing in von Gierke disease (type I)."),
    Enzyme("glycogen_phosphorylase", "Glycogen phosphorylase", "storage", "legendary",
           "Rate-limiting for glycogenolysis. Needs vitamin B6."),
    # The mitochondrion
    Enzyme("citrate_synthase", "Citrate synthase", "mito", "common",
           "First Krebs step: acetyl-CoA + oxaloacetate → citrate."),
    Enzyme("succinate_dh", "Succinate dehydrogenase", "mito", "common",
           "Double duty: a Krebs cycle enzyme and Complex II of the ETC."),
    Enzyme("akg_dh", "α-Ketoglutarate dehydrogenase", "mito", "common",
           "Same cofactors as PDH, so arsenite blocks it too."),
    Enzyme("pdh", "Pyruvate dehydrogenase", "mito", "rare",
           "Pyruvate → acetyl-CoA. Five cofactors: B1, lipoic acid, B2, B3, B5."),
    Enzyme("cox", "Cytochrome c oxidase", "mito", "rare",
           "Complex IV hands electrons to O₂. Cyanide, CO and azide block it."),
    Enzyme("cat1", "Carnitine acyltransferase I", "mito", "epic",
           "Rate-limiting for β-oxidation. Malonyl-CoA shuts it off."),
    Enzyme("atp_synthase", "ATP synthase", "mito", "epic",
           "Complex V: a rotary motor powered by protons. Oligomycin blocks it, so the gradient builds "
           "and electron transport stops."),
    Enzyme("isocitrate_dh", "Isocitrate dehydrogenase", "mito", "legendary",
           "Rate-limiting for the Krebs cycle. Activated by ADP; inhibited by ATP and NADH."),
    # Lipids & steroids
    Enzyme("fas", "Fatty acid synthase", "lipid", "common",
           "Builds palmitate two carbons at a time."),
    Enzyme("lpl", "Lipoprotein lipase", "lipid", "common",
           "Pulls fatty acids from chylomicrons and VLDL. Deficiency → type I hyperchylomicronemia."),
    Enzyme("lcat", "LCAT", "lipid", "common",
           "Esterifies cholesterol so HDL can mature."),
    Enzyme("mcad", "MCAD", "lipid", "rare",
           "Medium-chain acyl-CoA dehydrogenase. Deficiency → hypoketotic hypoglycemia after fasting."),
    Enzyme("hmgcoa_synthase", "HMG-CoA synthase", "lipid", "rare",
           "Rate-limiting for ketogenesis."),
    Enzyme("acc", "Acetyl-CoA carboxylase", "lipid", "epic",
           "Rate-limiting for fatty acid synthesis. Needs biotin; insulin and citrate switch it on."),
    Enzyme("desmolase", "Desmolase", "lipid", "epic",
           "Cholesterol side-chain cleavage, rate-limiting for steroid synthesis. "
           "ACTH drives it in the adrenals, LH in the gonads."),
    Enzyme("hmgcoa_reductase", "HMG-CoA reductase", "lipid", "legendary",
           "Rate-limiting for cholesterol synthesis. Statins block it."),
    # Urea cycle & nucleotides
    Enzyme("xanthine_oxidase", "Xanthine oxidase", "nitrogen", "common",
           "Makes uric acid. Allopurinol and febuxostat block it."),
    Enzyme("ada", "Adenosine deaminase", "nitrogen", "common",
           "Deficiency builds up toxic dATP and causes SCID."),
    Enzyme("rnr", "Ribonucleotide reductase", "nitrogen", "common",
           "Ribonucleotides → deoxyribonucleotides. Hydroxyurea blocks it."),
    Enzyme("otc", "Ornithine transcarbamylase", "nitrogen", "rare",
           "Most common urea cycle defect (X-linked). Orotic acid up, BUN down."),
    Enzyme("hgprt", "HGPRT", "nitrogen", "rare",
           "Purine salvage. Deficiency is Lesch-Nyhan: hyperuricemia, self-mutilation, dystonia."),
    Enzyme("cps2", "Carbamoyl phosphate synthetase II", "nitrogen", "epic",
           "Rate-limiting for pyrimidine synthesis. Works in the cytosol."),
    Enzyme("gppat", "Glutamine-PRPP amidotransferase", "nitrogen", "epic",
           "Rate-limiting for de novo purine synthesis."),
    Enzyme("cps1", "Carbamoyl phosphate synthetase I", "nitrogen", "legendary",
           "Rate-limiting for the urea cycle. Needs N-acetylglutamate to switch on."),
    # Heme & neurotransmitters
    Enzyme("dopa_decarboxylase", "DOPA decarboxylase", "amines", "common",
           "L-DOPA → dopamine. Carbidopa blocks it outside the brain."),
    Enzyme("mao", "Monoamine oxidase", "amines", "common",
           "Breaks down catecholamines and serotonin. MAOIs block it."),
    Enzyme("comt", "COMT", "amines", "common",
           "Also breaks down catecholamines. Entacapone and tolcapone block it."),
    Enzyme("ala_dehydratase", "ALA dehydratase", "amines", "rare",
           "Second step of heme synthesis. Lead inhibits it."),
    Enzyme("ferrochelatase", "Ferrochelatase", "amines", "rare",
           "Puts iron into protoporphyrin to make heme. Lead inhibits it too."),
    Enzyme("pah", "Phenylalanine hydroxylase", "amines", "epic",
           "Phenylalanine → tyrosine; needs BH4. Deficiency is PKU."),
    Enzyme("tyrosine_hydroxylase", "Tyrosine hydroxylase", "amines", "epic",
           "Rate-limiting for catecholamine synthesis."),
    Enzyme("ala_synthase", "ALA synthase", "amines", "legendary",
           "Rate-limiting for heme synthesis. Needs vitamin B6."),

]

ENZYME_BY_ID = {e.id: e for e in ENZYMES}
SET_BONUS = 0.05  # +5% ATP per completed set
CODEX_COMPLETE_BONUS = 0.10  # extra +10% when every set is complete

# Duplicates raise an enzyme's expression level. More copies of an enzyme mean a
# higher Vmax (Km stays the same), so each level above 1 adds a little ATP.
# Copies needed for levels 1..5; rarer enzymes turn up less often, so they need fewer.
EXPRESSION_COPIES = {
    "common": (1, 3, 6, 12, 20),
    "rare": (1, 3, 5, 9, 15),
    "epic": (1, 2, 4, 7, 10),
    "legendary": (1, 2, 3, 4, 6),
}
EXPRESSION_BONUS = 0.0025  # +0.25% ATP per expression level above 1, across the codex


def expression_level(copies: int, rarity: str = "common") -> int:
    return sum(1 for need in EXPRESSION_COPIES[rarity] if copies >= need)

# ---------------------------------------------------------------------------
# Cosmetics (the wardrobe)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cosmetic:
    id: str
    name: str
    slot: str  # hat | face | neck | skin | stage
    rarity: str
    source: str  # "drop" | "level:N" | "achievement:ID" | "pathway:ID" | "fission:N" | "default"


SLOTS = ("skin", "hat", "face", "neck", "stage")

COSMETICS: list[Cosmetic] = [
    # skins
    Cosmetic("skin_coral", "Classic coral", "skin", "common", "default"),
    Cosmetic("skin_gfp", "GFP green", "skin", "rare", "drop"),
    Cosmetic("skin_brownfat", "Brown fat", "skin", "rare", "drop"),
    Cosmetic("skin_golden", "Golden", "skin", "legendary", "drop"),
    Cosmetic("skin_galaxy", "Galaxy", "skin", "epic", "fission:1"),
    Cosmetic("skin_holo", "Holographic", "skin", "legendary", "fission:5"),
    # hats
    Cosmetic("hat_scrubcap", "Scrub cap", "hat", "common", "level:3"),
    Cosmetic("hat_beanie", "Beanie", "hat", "common", "drop"),
    Cosmetic("hat_party", "Party hat", "hat", "common", "drop"),
    Cosmetic("hat_grad", "Graduation cap", "hat", "rare", "level:30"),
    Cosmetic("hat_mirror", "Head mirror", "hat", "rare", "drop"),
    Cosmetic("hat_propeller", "Propeller cap", "hat", "epic", "drop"),
    Cosmetic("hat_halo", "Halo", "hat", "epic", "achievement:streak_100"),
    Cosmetic("hat_crown", "Crown", "hat", "legendary", "drop"),
    # face
    Cosmetic("face_glasses", "Round glasses", "face", "common", "level:5"),
    Cosmetic("face_mask", "Surgical mask", "face", "common", "drop"),
    Cosmetic("face_monocle", "Monocle", "face", "rare", "drop"),
    Cosmetic("face_shades", "Star shades", "face", "epic", "drop"),
    # neck
    Cosmetic("neck_bowtie", "Bow tie", "neck", "common", "drop"),
    Cosmetic("neck_badge", "Hospital badge", "neck", "common", "level:10"),
    Cosmetic("neck_stetho", "Stethoscope", "neck", "rare", "level:15"),
    Cosmetic("neck_scarf", "Cozy scarf", "neck", "rare", "drop"),
    Cosmetic("neck_medal", "Gold medal", "neck", "legendary", "achievement:streak_365"),
    # stages
    Cosmetic("stage_confocal", "Confocal", "stage", "common", "default"),
    Cosmetic("stage_he", "H&E slide", "stage", "rare", "drop"),
    Cosmetic("stage_gram", "Gram stain", "stage", "rare", "level:25"),
    Cosmetic("stage_em", "Electron micrograph", "stage", "epic", "drop"),
]

COSMETIC_BY_ID = {c.id: c for c in COSMETICS}
DEFAULT_EQUIPPED = {"skin": "skin_coral", "stage": "stage_confocal"}

# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

TITLES = [
    (1, "Pre-med"), (5, "MS1"), (10, "MS2"), (15, "Step 1 survivor"), (20, "MS3"),
    (25, "MS4"), (30, "Intern"), (35, "Resident"), (45, "Chief resident"),
    (55, "Fellow"), (65, "Attending"), (80, "Department chair"), (100, "Nobel laureate"),
]
LEVEL_ATP_BONUS = 0.01  # +1% ATP per level above 1


def xp_for_next(level: int) -> int:
    """XP needed to go from `level` to `level + 1`."""
    return int(round(60 + 32 * level ** 1.45))


def level_from_xp(xp: int) -> tuple[int, int, int]:
    """Return (level, xp_into_level, xp_needed_for_next)."""
    level = 1
    remaining = max(0, int(xp))
    while True:
        need = xp_for_next(level)
        if remaining < need:
            return level, remaining, need
        remaining -= need
        level += 1
        if level > 999:
            return level, 0, need


def title_for_level(level: int) -> str:
    title = TITLES[0][1]
    for lvl, name in TITLES:
        if level >= lvl:
            title = name
    return title


# ---------------------------------------------------------------------------
# Prestige ("Fission")
# ---------------------------------------------------------------------------

FISSION_BASE = 1e10  # all-time ATP needed for the first mtDNA copy
MTDNA_BONUS = 0.25  # +25% ATP per mtDNA copy
# A division restarts Mito's own machinery (pathways and their boosts). Everything that isn't
# Mito's survives: your study habits, the cell's vesicle machinery and your flow upgrades.
FISSION_KEEPS = ("habit", "vesicle", "flow")
# Mito grows with his machinery: full size once his pathways make 10^MITO_FULL_LOG10 ATP a card.
MITO_FULL_LOG10 = 7.0
FISSION_SUGGEST_MIN = 3  # the game suggests dividing once it would gain at least this many copies...
FISSION_SUGGEST_SHARE = 1.0  # ...and at least as many copies as you already have (each one doubles them)


def mtdna_possible(atp_all_time: float) -> int:
    if atp_all_time <= 0:
        return 0
    return int((atp_all_time / FISSION_BASE) ** (1 / 3) + 1e-9)


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    desc: str
    tier: str  # vesicle rarity granted when unlocked
    check: Callable[[dict], bool] = field(compare=False)
    hidden: bool = False


def _a(id, name, desc, tier, check, hidden=False) -> Achievement:
    return Achievement(id, name, desc, tier, check, hidden)


ACHIEVEMENTS: list[Achievement] = [
    _a("powerhouse", "The powerhouse of the cell", "Open Powerhouse for the first time.", "rare",
       lambda s: s["opened_game"]),
    _a("first_rep", "First rep", "Answer a card with Powerhouse running.", "common",
       lambda s: s["answers_total"] >= 1),
    _a("warm_up", "Warming up", "Answer 100 cards.", "common", lambda s: s["answers_total"] >= 100),
    _a("kilorep", "Kilorep", "Answer 1,000 cards.", "rare", lambda s: s["answers_total"] >= 1_000),
    _a("card_shark", "Card shark", "Answer 5,000 cards.", "rare", lambda s: s["answers_total"] >= 5_000),
    _a("ten_k", "Ten thousand reps", "Answer 10,000 cards.", "epic", lambda s: s["answers_total"] >= 10_000),
    _a("spaced_out", "Spaced out", "Answer 25,000 cards.", "epic", lambda s: s["answers_total"] >= 25_000),
    _a("ltp", "Long-term potentiation", "Answer 50,000 cards.", "epic", lambda s: s["answers_total"] >= 50_000),
    _a("six_figures", "Six figures", "Answer 100,000 cards.", "legendary",
       lambda s: s["answers_total"] >= 100_000),
    _a("living_textbook", "Living textbook", "Answer 250,000 cards.", "legendary",
       lambda s: s["answers_total"] >= 250_000),
    _a("day_200", "Clinic day", "Answer 200 cards in one day.", "common", lambda s: s["best_day"] >= 200),
    _a("day_500", "Busy shift", "Answer 500 cards in one day.", "rare", lambda s: s["best_day"] >= 500),
    _a("day_1000", "Call night", "Answer 1,000 cards in one day.", "rare", lambda s: s["best_day"] >= 1_000),
    _a("day_1500", "Dedicated", "Answer 1,500 cards in one day.", "epic", lambda s: s["best_day"] >= 1_500),
    _a("day_2000", "Boards eve", "Answer 2,000 cards in one day.", "legendary", lambda s: s["best_day"] >= 2_000),
    _a("streak_3", "Three-peat", "Hit your daily goal 3 days in a row.", "common", lambda s: s["best_streak"] >= 3),
    _a("streak_7", "Week one", "Keep a 7-day streak.", "rare", lambda s: s["best_streak"] >= 7),
    _a("streak_14", "Fortnight", "Keep a 14-day streak.", "rare", lambda s: s["best_streak"] >= 14),
    _a("streak_30", "Habit formed", "Keep a 30-day streak.", "epic", lambda s: s["best_streak"] >= 30),
    _a("streak_60", "Two months strong", "Keep a 60-day streak.", "epic", lambda s: s["best_streak"] >= 60),
    _a("streak_100", "Centurion", "Keep a 100-day streak. Unlocks the halo.", "legendary",
       lambda s: s["best_streak"] >= 100),
    _a("streak_200", "Iron will", "Keep a 200-day streak.", "legendary", lambda s: s["best_streak"] >= 200),
    _a("streak_365", "Year-round", "Keep a 365-day streak. Unlocks the gold medal.", "legendary",
       lambda s: s["best_streak"] >= 365),
    _a("flow_25", "In the zone", "Reach a flow of 25.", "common", lambda s: s["flow_best"] >= 25),
    _a("flow_50", "Momentum", "Reach a flow of 50.", "common", lambda s: s["flow_best"] >= 50),
    _a("flow_100", "Locked in", "Reach a flow of 100.", "rare", lambda s: s["flow_best"] >= 100),
    _a("flow_250", "Hyperfocus", "Reach a flow of 250.", "epic", lambda s: s["flow_best"] >= 250),
    _a("flow_500", "Monk mode", "Reach a flow of 500.", "legendary", lambda s: s["flow_best"] >= 500),
    _a("first_buy", "Investing in yourself", "Buy your first pathway.", "common", lambda s: s["purchases"] >= 1),
    _a("sugar_rush", "Sugar rush", "Own 25 Glycolysis.", "common",
       lambda s: s["owned"].get("glycolysis", 0) >= 25),
    _a("rotary", "Rotary engine", "Own an ATP synthase.", "rare", lambda s: s["owned"].get("synthase", 0) >= 1),
    _a("stay_warm", "One slow red ox", "Own some slow-twitch fibers.", "epic",
       lambda s: s["owned"].get("brownfat", 0) >= 1),
    _a("self_replicating", "Self-replicating", "Own Mitochondrial biogenesis.", "legendary",
       lambda s: s["owned"].get("biogenesis", 0) >= 1),
    _a("high_yield", "High yield", "Earn 1,000 ATP per card.", "rare", lambda s: s["per_card"] >= 1_000),
    _a("very_high_yield", "Very high yield", "Earn 1 million ATP per card.", "epic",
       lambda s: s["per_card"] >= 1_000_000),
    _a("atp_1m", "Millionaire", "Make 1 million ATP in total.", "common", lambda s: s["atp_all_time"] >= 1e6),
    _a("atp_1b", "Billionaire", "Make 1 billion ATP in total.", "rare", lambda s: s["atp_all_time"] >= 1e9),
    _a("atp_1t", "Trillionaire", "Make 1 trillion ATP in total.", "epic", lambda s: s["atp_all_time"] >= 1e12),
    _a("first_enzyme", "Catalyst", "Collect your first enzyme.", "common", lambda s: s["codex_unique"] >= 1),
    _a("first_legendary", "Rate-limiting", "Collect a legendary enzyme. Every legendary is a pathway's "
       "rate-limiting enzyme.", "epic",
       lambda s: s["legendary_enzymes"] >= 1),
    _a("set_complete", "Pathway complete", "Complete an enzyme set.", "epic", lambda s: s["sets_complete"] >= 1),
    _a("codex_complete", "Enzyme encyclopedia", "Collect every enzyme.", "legendary",
       lambda s: s["codex_unique"] >= len(ENZYMES)),
    _a("ves_1", "Exocytosis", "Open a vesicle.", "common", lambda s: s["vesicles_opened"] >= 1),
    _a("ves_100", "Secretory cell", "Open 100 vesicles.", "rare", lambda s: s["vesicles_opened"] >= 100),
    _a("ves_500", "Plasma cell", "Open 500 vesicles.", "epic", lambda s: s["vesicles_opened"] >= 500),
    _a("quest_1", "On the list", "Finish a daily quest.", "common", lambda s: s["quests_completed"] >= 1),
    _a("quest_day", "Triple threat", "Finish all three quests in one day.", "rare",
       lambda s: s["quest_full_days"] >= 1),
    _a("quest_50", "Reliable", "Finish 50 daily quests.", "epic", lambda s: s["quests_completed"] >= 50),
    _a("early_bird", "Early bird", "Answer 50 cards before 8 a.m. in one day.", "rare",
       lambda s: s["early_best"] >= 50),
    _a("weekend", "Weekend warrior", "Hit your goal on a Saturday and the Sunday after it.", "rare",
       lambda s: s["weekend_pairs"] >= 1),
    _a("comeback", "Comeback kid", "Come back after 3 or more days away.", "rare",
       lambda s: s["comebacks"] >= 1),
    _a("sweep_1", "Clean sweep", "Finish every due review for the day.", "rare", lambda s: s["sweeps"] >= 1),
    _a("sweep_7", "Inbox zero", "Finish every due review on 7 different days.", "epic",
       lambda s: s["sweeps"] >= 7),
    _a("fission_1", "Binary fission", "Divide for the first time.", "epic", lambda s: s["fissions"] >= 1),
    _a("fission_5", "Mitochondrial Eve", "Divide five times.", "legendary", lambda s: s["fissions"] >= 5),
    _a("poke_50", "Please stop poking me", "Poke Mito 50 times.", "common", lambda s: s["pokes"] >= 50,
       hidden=True),
]

ACHIEVEMENT_BY_ID = {a.id: a for a in ACHIEVEMENTS}
ACHIEVEMENT_ATP_BONUS = 0.01  # +1% ATP per achievement unlocked

# ---------------------------------------------------------------------------
# Daily quests
# ---------------------------------------------------------------------------

QUEST_REWARD_RARITY = {"easy": "common", "medium": "rare", "spice": "rare"}
QUEST_ALL_BONUS_RARITY = "epic"
QUEST_REWARD_CARDS = {"easy": 30, "medium": 60, "spice": 60}

SPICE_TEMPLATES = ("flow", "noon", "sessions", "vesicles", "sweep")

# ---------------------------------------------------------------------------
# Mito's lines when poked
# ---------------------------------------------------------------------------

POKE_LINES = [
    "I'm the powerhouse of the cell. Act like it.",
    "Poking me makes 0 ATP. Cards make ATP.",
    "Did you know I have my own DNA? It came from your mom.",
    "Cyanide is my least favorite word.",
    "Every card you answer makes me stronger.",
    "Again, Hard, Good, Easy: same ATP. Be honest with yourself.",
    "Spaced repetition beats cramming. I've seen the data.",
    "I used to be a free-living bacterium, you know.",
    "Drink some water. Your neurons will thank you.",
    "Brown fat is just me, but warmer.",
    "Ten more cards? I believe in you.",
    "My inner membrane is very folded. Like your attention after hour three.",
    "Oligomycin? Never heard of her.",
    "Sleep is when memories consolidate. Don't skip it.",
    "Please stop poking me. Unless it's for science.",
]
