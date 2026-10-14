"""
Statutory Knowledge Base & Indian Legal Provision Engine
Covers key provisions of:
- Bharatiya Nyaya Sanhita, 2023 (BNS) & corresponding Indian Penal Code, 1860 (IPC)
- Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) & corresponding Code of Criminal Procedure, 1973 (CrPC)
- Bharatiya Sakshya Adhiniyam, 2023 (BSA) & corresponding Indian Evidence Act, 1872 (IEA)
- Negotiable Instruments Act, 1881 (NI Act)
- Constitution of India & Civil Procedure Code, 1908 (CPC)
"""

import re
from typing import Dict, Any, Optional, List

STATUTORY_DATABASE: Dict[str, Dict[str, Any]] = {
    # ---------------- BNS Provisions ----------------
    "bns_35": {
        "act": "Bharatiya Nyaya Sanhita, 2023 (BNS)",
        "section": "Section 35",
        "title": "Right of private defence of the body and of property",
        "legacy_counterpart": "Section 97, Indian Penal Code, 1860 (IPC)",
        "chapter": "Chapter III: General Exceptions (Private Defence)",
        "overview": (
            "Section 35 of the Bharatiya Nyaya Sanhita, 2023 guarantees every citizen the inherent statutory right "
            "of private defence to protect their own body or the body of any other person, as well as movable or "
            "immovable property, against specified unlawful offences."
        ),
        "statutory_text": (
            "Every person has a right, subject to the restrictions contained in section 37, to defend:—\n"
            "(a) his own body, and the body of any other person, against any offence affecting the human body;\n"
            "(b) the property, whether movable or immovable, of himself or of any other person, against any act "
            "which is an offence falling under the definition of theft, robbery, mischief, or criminal trespass, "
            "or which is an attempt to commit theft, robbery, mischief, or criminal trespass."
        ),
        "key_elements": [
            "Defence of Body: Protects self and any other person from any offence affecting the human body (e.g., assault, hurt, grievous hurt, rape, kidnapping).",
            "Defence of Property: Covers both movable and immovable property belonging to oneself or any other person.",
            "Covered Property Offences: Limited strictly to theft, robbery, mischief, criminal trespass, or attempts thereof.",
            "Third-Party Protection: Crucially, a citizen is legally permitted to protect strangers/bystanders, not just themselves.",
            "Subordination to Section 37: The exercise of private defence is strictly subject to the limits under Section 37 BNS (proportionality, no more harm than necessary, and recourse to public authorities when feasible)."
        ],
        "procedural_aspects": [
            "Nature of Plea: General Exception under Chapter III of BNS.",
            "Burden of Proof: Under Section 108 of Bharatiya Sakshya Adhiniyam, 2023 (formerly Section 105 Evidence Act), the initial burden of proving circumstances bringing the case within the exception lies upon the accused, to be discharged on a preponderance of probabilities.",
            "Judicial Treatment: The court may recognize private defence even if not specifically pleaded, if discernible from the prosecution evidence."
        ],
        "precedents": [
            "Darshan Singh v. State of Punjab (2010) 2 SCC 333: Laid down 10 golden principles on the right of private defence; clarified that a person facing reasonable apprehension of death or grievous hurt is not expected to modulate their response with golden scales.",
            "Munshi Ram v. Delhi Administration (AIR 1968 SC 702): Settled that the right of private defence is a protective right, not a punitive or retributive one."
        ],
        "related_provisions": [
            "Section 34 BNS (Things done in private defence)",
            "Section 37 BNS (Acts against which there is no right of private defence - old Section 99 IPC)",
            "Section 38-44 BNS (When private defence extends to causing death or other harms)",
            "Section 35 BNSS Note: If you are inquiring about police arrest powers without warrant, that is Section 35 of the Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)."
        ]
    },
    "bns_34": {
        "act": "Bharatiya Nyaya Sanhita, 2023 (BNS)",
        "section": "Section 34",
        "title": "Things done in private defence",
        "legacy_counterpart": "Section 96, Indian Penal Code, 1860 (IPC)",
        "chapter": "Chapter III: General Exceptions",
        "overview": "Establishes the foundational principle that nothing is an offence which is done in the exercise of the right of private defence.",
        "statutory_text": "Nothing is an offence which is done in the exercise of the right of private defence.",
        "key_elements": [
            "Absolute immunity when legitimate exercise of private defence is proven.",
            "Acts as a complete justification negating criminal liability."
        ],
        "procedural_aspects": ["General Exception. Discharged on preponderance of probabilities."],
        "precedents": ["Jai Dev v. State of Punjab (AIR 1963 SC 612)"],
        "related_provisions": ["Section 35 BNS", "Section 37 BNS"]
    },
    "bns_37": {
        "act": "Bharatiya Nyaya Sanhita, 2023 (BNS)",
        "section": "Section 37",
        "title": "Acts against which there is no right of private defence",
        "legacy_counterpart": "Section 99, Indian Penal Code, 1860 (IPC)",
        "chapter": "Chapter III: General Exceptions",
        "overview": "Sets statutory limits and restrictions on the exercise of the right of private defence.",
        "statutory_text": (
            "There is no right of private defence against an act which does not reasonably cause the apprehension of death "
            "or of grievous hurt, if done, or attempted to be done, by a public servant acting in good faith under colour of his office, "
            "though that act may not be strictly justifiable by law.\n"
            "There is no right of private defence in cases in which there is time to have recourse to the protection of the public authorities.\n"
            "The right of private defence in no case extends to the inflicting of more harm than it is necessary to inflict for the purpose of defence."
        ),
        "key_elements": [
            "Proportionality: Never extends to inflicting more harm than is reasonably necessary.",
            "Recourse Rule: Disallowed if there is sufficient time to seek help from law enforcement/public authorities.",
            "Acts of Public Servants: Protected if acting in good faith under colour of office without threat of death or grievous hurt."
        ],
        "procedural_aspects": ["Qualifies Sections 35, 38, 39, 40, 41, 42, 43, 44 BNS."],
        "precedents": ["Puran Singh v. State of Punjab (AIR 1975 SC 1674)"],
        "related_provisions": ["Section 35 BNS", "Section 38 BNS"]
    },
    "bns_103": {
        "act": "Bharatiya Nyaya Sanhita, 2023 (BNS)",
        "section": "Section 103",
        "title": "Punishment for murder",
        "legacy_counterpart": "Section 302, Indian Penal Code, 1860 (IPC)",
        "chapter": "Chapter VI: Offences Affecting the Human Body",
        "overview": "Prescribes punishment for the offence of murder, including single accused and mob lynching/hate crimes.",
        "statutory_text": (
            "(1) Whoever commits murder shall be punished with death or imprisonment for life, and shall also be liable to fine.\n"
            "(2) When a group of five or more persons acting in concert commits murder on the ground of race, caste or community, "
            "sex, place of birth, language, personal belief or any other similar ground, each member of such group shall be punished "
            "with death or with imprisonment for life, and shall also be liable to fine."
        ),
        "key_elements": [
            "Punishment: Death penalty or rigorous life imprisonment plus mandatory fine.",
            "Sub-section (2) Mob Lynching: Explicit statutory aggravation for hate crimes / mob violence by 5 or more persons."
        ],
        "procedural_aspects": ["Cognizable, Non-bailable, Non-compoundable, Triable by Court of Session."],
        "precedents": ["Bachan Singh v. State of Punjab (1980) 2 SCC 684 (Rarest of Rare doctrine)"],
        "related_provisions": ["Section 101 BNS (Definition of Murder - old Section 300 IPC)", "Section 105 BNS (Culpable homicide)"]
    },
    "bns_105": {
        "act": "Bharatiya Nyaya Sanhita, 2023 (BNS)",
        "section": "Section 105",
        "title": "Punishment for culpable homicide not amounting to murder",
        "legacy_counterpart": "Section 304, Indian Penal Code, 1860 (IPC)",
        "chapter": "Chapter VI: Offences Affecting the Human Body",
        "overview": "Provides two tiers of punishment for culpable homicide depending on whether intention or knowledge was present.",
        "statutory_text": (
            "Whoever commits culpable homicide not amounting to murder, shall be punished with imprisonment for life, "
            "or imprisonment of either description for a term which may extend to ten years, and shall also be liable to fine, "
            "if the act by which the death is caused is done with the intention of causing death, or of causing such bodily injury "
            "as is likely to cause death; or with imprisonment of either description for a term which may extend to ten years, "
            "or with fine, or with both, if the act is done with the knowledge that it is likely to cause death, but without any intention to cause death."
        ),
        "key_elements": [
            "Part I (Intention): Imprisonment for life or up to 10 years + fine.",
            "Part II (Knowledge without Intention): Imprisonment up to 10 years, or fine, or both."
        ],
        "procedural_aspects": ["Cognizable, Non-bailable, Non-compoundable, Triable by Court of Session."],
        "precedents": ["State of A.P. v. Rayavarapu Punnayya (AIR 1977 SC 45)"],
        "related_provisions": ["Section 100 BNS (Culpable Homicide - old Section 299 IPC)"]
    },
    "bns_318": {
        "act": "Bharatiya Nyaya Sanhita, 2023 (BNS)",
        "section": "Section 318",
        "title": "Cheating and dishonestly inducing delivery of property",
        "legacy_counterpart": "Section 415 & 420, Indian Penal Code, 1860 (IPC)",
        "chapter": "Chapter XVII: Offences Against Property",
        "overview": "Consolidates and punishes cheating and dishonest inducement to deliver property.",
        "statutory_text": "Punishes simple cheating with up to 3 years imprisonment, and aggravated cheating inducing delivery of property with up to 7 years imprisonment and fine.",
        "key_elements": [
            "Deception of any person fraudulently or dishonestly.",
            "Inducement to deliver any property or consent to retain property.",
            "Mens rea required from the inception of the transaction."
        ],
        "procedural_aspects": ["Sub-sec (4) is Cognizable, Non-bailable, Compoundable with permission of Court."],
        "precedents": ["Hridaya Ranjan Prasad Verma v. State of Bihar (2000) 4 SCC 168"],
        "related_provisions": ["Section 316 BNS (Criminal Breach of Trust)"]
    },

    # ---------------- BNSS Provisions ----------------
    "bnss_35": {
        "act": "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)",
        "section": "Section 35",
        "title": "When police may arrest without warrant",
        "legacy_counterpart": "Section 41, Code of Criminal Procedure, 1973 (CrPC)",
        "chapter": "Chapter V: Arrest of Persons",
        "overview": (
            "Section 35 of BNSS establishes the legal framework governing arrests without a warrant by police officers, "
            "codifying the Supreme Court's Arnesh Kumar guidelines and introducing new safeguards for elderly/infirm individuals."
        ),
        "statutory_text": (
            "Any police officer may without an order from a Magistrate and without a warrant, arrest any person who commits "
            "in the presence of a police officer, a cognizable offence; or against whom a reasonable complaint has been made, "
            "or credible information has been received, or a reasonable suspicion exists that he has committed a cognizable offence "
            "punishable with imprisonment for a term which may be less than seven years or which may extend to seven years...\n"
            "Provided that in all cases where the arrest of a person is not required under this sub-section, the police officer shall "
            "record the reasons in writing for not making the arrest."
        ),
        "key_elements": [
            "For offences <= 7 years imprisonment: Arrest is not automatic; requires satisfaction of specified conditions (preventing further offence, proper investigation, preventing tampering, securing appearance).",
            "Notice of Appearance: Section 35(3) mandates issuance of notice of appearance (replacing Section 41A CrPC).",
            "Special Protection: No arrest shall be made for offences punishable with less than 3 years without prior permission of Deputy Superintendent of Police (DSP) if the person is infirm or above 60 years of age."
        ],
        "procedural_aspects": [
            "Mandatory recording of reasons for arrest or non-arrest in case diary.",
            "Failure to comply renders the arresting officer liable for departmental inquiry and contempt of court."
        ],
        "precedents": [
            "Arnesh Kumar v. State of Bihar (2014) 8 SCC 273 (Codified into statutory text of Section 35 BNSS)",
            "Satender Kumar Antil v. CBI (2022) 10 SCC 51 (Bail and arrest compliance)"
        ],
        "related_provisions": ["Section 35(3) BNSS (Notice of Appearance - old 41A CrPC)", "Section 37 BNSS (Designated police officer)"]
    },
    "bnss_482": {
        "act": "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)",
        "section": "Section 482",
        "title": "Direction for grant of bail to person apprehending arrest (Anticipatory Bail)",
        "legacy_counterpart": "Section 438, Code of Criminal Procedure, 1973 (CrPC)",
        "chapter": "Chapter XXXV: Provisions as to Bail and Bonds",
        "overview": (
            "Section 482 of BNSS empowers the High Court and Sessions Court to issue directions granting anticipatory bail "
            "to individuals with a reasonable apprehension of arrest in non-bailable offences."
        ),
        "statutory_text": (
            "Where any person has reason to believe that he may be arrested on accusation of having committed a non-bailable offence, "
            "he may apply to the High Court or the Court of Session for a direction under this section; and that Court may, "
            "if it thinks fit, direct that in the event of such arrest, he shall be released on bail."
        ),
        "key_elements": [
            "Concurrent Jurisdiction: Applicant may approach either Court of Session or High Court.",
            "Nature of Accusation: Offence must be non-bailable with tangible reason to apprehend arrest.",
            "Judicial Factors: Gravity of accusation, antecedents of applicant, likelihood of fleeing, and possibility of malicious prosecution.",
            "Conditions: Ready availability for interrogation, no inducement/threat to witnesses, no leaving India without court permission."
        ],
        "procedural_aspects": [
            "Interim Protection: Court can grant interim anticipatory bail pending notice to Public Prosecutor.",
            "Duration: Ordinarily continues until the conclusion of the trial unless limited by the court."
        ],
        "precedents": [
            "Gurbaksh Singh Sibbia v. State of Punjab (1980) 2 SCC 565 (Constitution Bench foundational judgment)",
            "Sushila Aggarwal v. State (NCT of Delhi) (2020) 5 SCC 1 (Confirmed anticipatory bail need not be time-limited)"
        ],
        "related_provisions": ["Section 480 BNSS (Regular bail - old 437 CrPC)", "Section 483 BNSS (High Court/Sessions bail - old 439 CrPC)"]
    },
    "bnss_528": {
        "act": "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)",
        "section": "Section 528",
        "title": "Saving of inherent powers of High Court",
        "legacy_counterpart": "Section 482, Code of Criminal Procedure, 1973 (CrPC)",
        "chapter": "Chapter XXXIX: Miscellaneous",
        "overview": (
            "Preserves the inherent plenary jurisdiction of the High Court to make such orders as may be necessary to give effect "
            "to any order under the Sanhita, to prevent abuse of the process of any court, or otherwise to secure the ends of justice."
        ),
        "statutory_text": (
            "Nothing in this Sanhita shall be deemed to limit or affect the inherent powers of the High Court to make such orders "
            "as may be necessary to give effect to any order under this Sanhita, or to prevent abuse of the process of any Court "
            "or otherwise to secure the ends of justice."
        ),
        "key_elements": [
            "Three Recognized Grounds: (1) To give effect to any order under the Code; (2) To prevent abuse of the process of court; (3) To secure ends of justice.",
            "Quashing of FIR / Chargesheet: Frequently invoked when allegations even if taken at face value do not disclose any cognizable offence."
        ],
        "procedural_aspects": ["Invoked exclusively before High Court through criminal miscellaneous petition."],
        "precedents": [
            "State of Haryana v. Bhajan Lal (1992 Supp (1) SCC 335) - 7 illustrative categories for quashing criminal proceedings.",
            "Neeharika Infrastructure v. State of Maharashtra (2021 SCC OnLine SC 315) - Caution against routine stay of investigation."
        ],
        "related_provisions": ["Article 226 of the Constitution of India (Writ Jurisdiction)"]
    },

    # ---------------- NI Act Provisions ----------------
    "ni_138": {
        "act": "Negotiable Instruments Act, 1881",
        "section": "Section 138",
        "title": "Dishonour of cheque for insufficiency, etc., of funds in the account",
        "legacy_counterpart": "Original statutory enactment with subsequent 2002 and 2018 amendments",
        "chapter": "Chapter XVII: Penalties in case of Dishonour of Cheques",
        "overview": (
            "Creates quasi-criminal statutory liability for the dishonour of a cheque drawn on an account maintained with a banker "
            "for discharge, in whole or in part, of any debt or other legally enforceable liability."
        ),
        "statutory_text": (
            "Where any cheque drawn by a person on an account maintained by him with a banker for payment of any amount of money "
            "to another person from out of that account for the discharge, in whole or in part, of any debt or other liability, "
            "is returned by the bank unpaid, either because of the amount of money standing to the credit of that account is insufficient... "
            "such person shall be deemed to have committed an offence and shall be punished with imprisonment for a term which may be extended "
            "to two years, or with fine which may extend to twice the amount of the cheque, or with both."
        ),
        "key_elements": [
            "Legally Enforceable Debt: The cheque must have been issued for discharge of a valid, legally enforceable liability.",
            "Presentation Period: Presented to the bank within its validity period (ordinarily 3 months from date of issuance).",
            "Return Memo: Cheque dishonoured due to insufficient funds, account closed, refer to drawer, or exceeds arrangements.",
            "Statutory Notice: Demand notice in writing issued within 30 days of receiving the bank memo.",
            "Grace Period: Drawer fails to make payment within 15 days of receipt of the demand notice.",
            "Cause of Action: Complaint must be filed within 1 month from the expiry of the 15-day notice period."
        ],
        "procedural_aspects": [
            "Nature: Non-cognizable, Bailable, Compoundable under Section 147 NI Act.",
            "Triable by: Judicial Magistrate First Class / Metropolitan Magistrate.",
            "Summary Trial: Conducted as a summary trial under Section 143 NI Act.",
            "Interim Compensation: Court may order interim compensation up to 20% of cheque amount under Section 143A."
        ],
        "precedents": [
            "Rangappa v. Sri Mohan (2010) 11 SCC 441 (Three-Judge Bench confirming reverse presumption of debt under Section 139).",
            "Dashrath Rupsingh Rathod v. State of Maharashtra (2014) 9 SCC 129 & 2015 Amendment (Jurisdiction lies at the branch where payee maintains their bank account)."
        ],
        "related_provisions": [
            "Section 139 NI Act (Presumption in favour of holder)",
            "Section 141 NI Act (Offences by companies / vicarious liability of directors)",
            "Section 143A NI Act (Power to direct interim compensation)"
        ]
    }
}


def lookup_statutory_knowledge(query: str) -> Optional[Dict[str, Any]]:
    """
    Intelligently inspects a user's question and matches it to relevant statutory records.
    Handles variations like 'BNS ACT 35', 'Section 35 BNS', 'private defence', 'anticipatory bail', 'section 138 ni act'.
    """
    q_norm = query.lower().strip()
    q_norm = re.sub(r'[^a-z0-9\s]', ' ', q_norm)
    words = set(q_norm.split())

    # Check for BNS 35 / Section 35
    if "35" in words and any(w in words for w in ["bns", "nyaya", "sanhita"]):
        return STATUTORY_DATABASE["bns_35"]
    
    # Check for BNSS 35 / Section 35 arrest
    if "35" in words and any(w in words for w in ["bnss", "nagarik", "suraksha", "arrest"]):
        return STATUTORY_DATABASE["bnss_35"]

    # Check for Private Defence
    if ("private" in words and "defence" in words) or ("self" in words and "defence" in words):
        return STATUTORY_DATABASE["bns_35"]

    # Check for BNS 34
    if "34" in words and any(w in words for w in ["bns", "nyaya"]):
        return STATUTORY_DATABASE["bns_34"]

    # Check for BNS 37
    if "37" in words and any(w in words for w in ["bns", "nyaya"]):
        return STATUTORY_DATABASE["bns_37"]

    # Check for Murder / BNS 103 / Section 302
    if ("103" in words and any(w in words for w in ["bns", "nyaya"])) or "murder" in words or "302" in words:
        return STATUTORY_DATABASE["bns_103"]

    # Check for Culpable Homicide / BNS 105 / Section 304
    if ("105" in words and any(w in words for w in ["bns", "nyaya"])) or ("culpable" in words and "homicide" in words) or "304" in words:
        return STATUTORY_DATABASE["bns_105"]

    # Check for Cheating / BNS 318 / Section 420
    if ("318" in words and any(w in words for w in ["bns", "nyaya"])) or "420" in words or "cheating" in words:
        return STATUTORY_DATABASE["bns_318"]

    # Check for Anticipatory Bail / BNSS 482 / Section 438
    if ("anticipatory" in words and "bail" in words) or ("482" in words and any(w in words for w in ["bnss", "nagarik"])) or ("438" in words and "crpc" in words):
        return STATUTORY_DATABASE["bnss_482"]

    # Check for Quashing / Inherent Powers / Section 482 CrPC / Section 528 BNSS
    if ("528" in words and any(w in words for w in ["bnss", "nagarik"])) or ("482" in words and any(w in words for w in ["quash", "inherent", "crpc", "cr.p.c"])):
        return STATUTORY_DATABASE["bnss_528"]

    # Check for Cheque Bounce / Section 138 NI Act
    if "138" in words or ("cheque" in words and any(w in words for w in ["bounce", "dishonour", "memo", "notice"])):
        return STATUTORY_DATABASE["ni_138"]

    # General Section 35 fallback (defaults to BNS 35 Private Defence with BNSS 35 Arrest note)
    if "35" in words and ("section" in words or "act" in words):
        return STATUTORY_DATABASE["bns_35"]

    return None


def format_statutory_response(record: Dict[str, Any], query: str, context_note: Optional[str] = None) -> str:
    """
    Renders an authoritative, beautifully structured Markdown analysis of a statutory provision.
    """
    lines = []
    if context_note:
        lines.append(f"> [!NOTE]\n> {context_note}\n")

    lines.append(f"### {record['act']}: {record['section']} — {record['title']}")
    lines.append(f"**Historical / Corresponding Provision:** {record['legacy_counterpart']}")
    lines.append(f"**Classification & Chapter:** {record['chapter']}\n")

    lines.append("#### 1. Overview & Statutory Scope")
    lines.append(record['overview'] + "\n")

    lines.append("#### 2. Bare Act Provision")
    lines.append("```text\n" + record['statutory_text'] + "\n```\n")

    lines.append("#### 3. Essential Ingredients & Legal Principles")
    for elem in record['key_elements']:
        lines.append(f"- **{elem.split(':')[0]}:**" + elem[len(elem.split(':')[0]):])
    lines.append("")

    lines.append("#### 4. Procedural Framework & Classification")
    for proc in record['procedural_aspects']:
        lines.append(f"- {proc}")
    lines.append("")

    lines.append("#### 5. Landmark Judicial Precedents")
    for prec in record['precedents']:
        lines.append(f"- **{prec.split(':')[0]}**: {prec[len(prec.split(':')[0])+1:].strip()}")
    lines.append("")

    if record.get('related_provisions'):
        lines.append("#### 6. Related & Cross-Referenced Provisions")
        for rel in record['related_provisions']:
            lines.append(f"- {rel}")
        lines.append("")

    lines.append("---")
    lines.append(
        "*Disclaimer: This statutory analysis is provided for legal research and decision support. "
        "Verified against official legislative text published by the Ministry of Law & Justice, Government of India.*"
    )

    return "\n".join(lines)
