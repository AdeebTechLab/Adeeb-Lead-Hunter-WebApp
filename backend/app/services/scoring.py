from __future__ import annotations

from typing import Any, Dict, List, Tuple

SERVICES = {
    "website": "Website Development",
    "seo": "SEO",
    "social": "Social Media Marketing",
    "automation": "AI Automation",
    "va": "Virtual Assistant Services",
}

SERVICE_VALUE = {
    "Website Development": "a fast, mobile-first website that turns searches into calls, WhatsApp conversations and bookings",
    "SEO": "local search improvements that help the business appear for high-intent customer searches",
    "Social Media Marketing": "a consistent content and campaign system that builds trust and produces enquiries",
    "AI Automation": "automated WhatsApp, enquiry, booking and follow-up workflows that reduce missed opportunities",
    "Virtual Assistant Services": "a reliable support workflow for lead follow-up, scheduling, data entry and customer coordination",
}


def score_profile(score: int) -> Dict[str, str]:
    if score >= 90:
        return {
            "band": "90–100",
            "label": "Top-priority opportunity",
            "meaning": "Multiple verified sales opportunities, strong public demand signals and a usable contact path. Contact first.",
            "action": "Call today, reference the strongest audit finding and ask for a short discovery meeting.",
        }
    if score >= 75:
        return {
            "band": "75–89",
            "label": "Hot lead",
            "meaning": "Clear service need with enough evidence and contactability to justify immediate outreach.",
            "action": "Prioritize in the current calling block and follow up within 24 hours.",
        }
    if score >= 65:
        return {
            "band": "65–74",
            "label": "Strong warm lead",
            "meaning": "Good fit and visible opportunity, but one or two signals still need confirmation.",
            "action": "Contact after hot leads and use discovery questions to verify the missing signals.",
        }
    if score >= 50:
        return {
            "band": "50–64",
            "label": "Warm lead",
            "meaning": "A credible opportunity exists, although contact details, urgency or audit evidence may be incomplete.",
            "action": "Research the contact path, then run a focused call or WhatsApp outreach.",
        }
    if score >= 40:
        return {
            "band": "40–49",
            "label": "Cold / incomplete lead",
            "meaning": "Some need is visible, but the record is difficult to contact or lacks enough verified evidence.",
            "action": "Enrich the phone, email, website and social data before assigning sales time.",
        }
    return {
        "band": "0–39",
        "label": "Low-confidence lead",
        "meaning": "The available public data does not yet prove a strong or reachable sales opportunity.",
        "action": "Do not prioritize. Verify the business and collect stronger evidence first.",
    }


def score_lead(lead: Dict[str, Any], audit: Dict[str, Any] | None = None) -> Tuple[int, str, str, List[str]]:
    audit = audit or lead.get("audit") or {}
    score = 18
    reasons: List[str] = []
    opportunities = {key: 0 for key in SERVICES}

    if not lead.get("website"):
        score += 30
        opportunities["website"] += 8
        reasons.append("Website missing")
    else:
        score += 7
        if audit:
            if not audit.get("ssl_enabled", False):
                score += 10
                opportunities["website"] += 4
                reasons.append("SSL is not enabled")
            if not audit.get("mobile_friendly", False):
                score += 8
                opportunities["website"] += 4
                reasons.append("Website is not mobile friendly")
            seo_score = int(audit.get("seo_score", 0) or 0)
            if seo_score < 60:
                score += 12
                opportunities["seo"] += 7
                reasons.append(f"Basic SEO score is {seo_score}/100")
            if not audit.get("contact_form", False):
                score += 4
                opportunities["website"] += 2
                reasons.append("Contact form missing")
            if not audit.get("whatsapp_button", False):
                score += 6
                opportunities["automation"] += 4
                reasons.append("WhatsApp conversion path missing")
            if not audit.get("booking_system", False) and lead.get("category", "").lower() in {
                "clinic", "dental clinic", "beauty salon", "hotel", "restaurant", "gym", "hospital", "salon", "spa"
            }:
                score += 5
                opportunities["automation"] += 3
                reasons.append("Online booking opportunity")
            broken = int(audit.get("broken_links", 0) or 0)
            if broken:
                score += min(8, broken * 2)
                opportunities["website"] += 2
                reasons.append(f"{broken} broken link checks found")

    socials = [lead.get("facebook"), lead.get("instagram"), lead.get("linkedin")]
    social_count = sum(bool(item) for item in socials)
    if social_count == 0:
        score += 12
        opportunities["social"] += 7
        reasons.append("Social profiles missing or not found")
    elif social_count == 1:
        score += 7
        opportunities["social"] += 4
        reasons.append("Limited social presence")
    else:
        score += 4
        reasons.append("Multiple public social profiles found")

    reviews = int(lead.get("reviews_count", 0) or 0)
    if reviews >= 300:
        score += 10
        reasons.append("Strong public customer engagement")
    elif reviews >= 80:
        score += 6
        reasons.append("Established public engagement")
    elif reviews >= 20:
        score += 3
        reasons.append("Some public customer engagement")

    if lead.get("phone"):
        score += 7
        reasons.append("Direct phone contact available")
    if lead.get("email"):
        score += 4
        reasons.append("Public email contact available")
    if lead.get("website") and not lead.get("phone") and not lead.get("email"):
        score += 1
    if not lead.get("phone") and not lead.get("email"):
        score -= 12
        reasons.append("Direct contact information is limited")

    if lead.get("contact_confidence") == "High":
        score += 3
    if lead.get("rating") and float(lead.get("rating") or 0) >= 4.2:
        score += 3

    if lead.get("category", "").lower() in {
        "real estate", "hospital", "hotel", "car dealership", "law firm", "travel agency", "school", "academy"
    }:
        opportunities["va"] += 2

    score = max(0, min(100, score))
    priority = "Hot" if score >= 75 else "Warm" if score >= 50 else "Cold"
    recommended_key = max(opportunities, key=opportunities.get)
    recommended_service = SERVICES[recommended_key]

    if not reasons:
        reasons.append("Public profile needs manual qualification")
    return score, priority, recommended_service, reasons[:8]


def build_score_breakdown(lead: Dict[str, Any], score: int) -> Dict[str, Any]:
    contactability = 20 if lead.get("phone") and lead.get("email") else 15 if lead.get("phone") else 9 if lead.get("email") else 4 if lead.get("website") else 0
    engagement = 20 if int(lead.get("reviews_count") or 0) >= 300 else 14 if int(lead.get("reviews_count") or 0) >= 80 else 8 if int(lead.get("reviews_count") or 0) >= 20 else 3
    opportunity = max(0, min(60, score - contactability - engagement))
    profile = score_profile(score)
    return {
        "total": score,
        "opportunity_signal": opportunity,
        "contactability": contactability,
        "engagement_signal": engagement,
        **profile,
    }


def build_summary(lead: Dict[str, Any], score: int, priority: str, service: str, reasons: List[str]) -> str:
    name = lead.get("business_name", "This business")
    city = lead.get("city", "its market")
    reason = reasons[0].lower() if reasons else "a visible digital growth opportunity"
    profile = score_profile(score)
    return (
        f"{name} is a {priority.lower()}-priority prospect in {city} because {reason}. "
        f"The {score}/100 score means: {profile['meaning']} Lead with {service}."
    )


def _contact_instruction(lead: Dict[str, Any]) -> str:
    if lead.get("phone"):
        return f"Call {lead['phone']} and ask for the owner, manager or person responsible for marketing and customer enquiries."
    if lead.get("email"):
        return f"Email {lead['email']} and use the Google Maps listing or website to identify the decision-maker before calling."
    if lead.get("website"):
        return "Use the website contact form and the Google Maps listing to identify the public phone number or decision-maker."
    return "Open the Google Maps listing from the lead record and verify a public phone number before outreach. Do not use an unverified number."


ROMAN_URDU_SERVICE_VALUE = {
    "Website Development": "ek fast aur mobile-friendly website jo customer ko search se call, WhatsApp ya booking tak asani se le jaye",
    "SEO": "local search mein behtari taa-ke high-intent customers ko business Google par zyada asani se nazar aaye",
    "Social Media Marketing": "consistent content aur campaign system jo trust banaye aur enquiries generate kare",
    "AI Automation": "WhatsApp, enquiry, booking aur follow-up ko automate karna taa-ke missed opportunities kam hon",
    "Virtual Assistant Services": "lead follow-up, scheduling, data entry aur customer coordination ke liye reliable support workflow",
}


def _roman_urdu_reason(reason: str) -> str:
    exact = {
        "Website missing": "website maujood nahin hai",
        "SSL is not enabled": "website par SSL security enabled nahin hai",
        "Website is not mobile friendly": "website mobile par properly optimized nahin hai",
        "Contact form missing": "website par contact form maujood nahin hai",
        "WhatsApp conversion path missing": "customer ke liye direct WhatsApp enquiry ka clear rasta maujood nahin hai",
        "Online booking opportunity": "online booking system add karne ka acha mauqa hai",
        "Social profiles missing or not found": "public social media profiles ya to maujood nahin hain ya verify nahin ho rahe",
        "Limited social presence": "social media presence limited hai",
        "Multiple public social profiles found": "multiple public social profiles maujood hain",
        "Strong public customer engagement": "public customer engagement strong nazar aa rahi hai",
        "Established public engagement": "public engagement achi aur established nazar aa rahi hai",
        "Some public customer engagement": "kuch public customer engagement nazar aa rahi hai",
        "Direct phone contact available": "direct phone contact available hai",
        "Public email contact available": "public email contact available hai",
        "Direct contact information is limited": "direct contact information limited hai",
        "Public profile needs manual qualification": "public profile ko thori manual verification ki zarurat hai",
    }
    if reason in exact:
        return exact[reason]
    if reason.startswith("Basic SEO score is "):
        score = reason.removeprefix("Basic SEO score is ")
        return f"basic SEO score {score} hai aur is mein behtari ki gunjaish hai"
    if " broken link checks found" in reason:
        number = reason.split(" ", 1)[0]
        return f"website audit mein {number} broken link checks mile hain"
    return reason.lower()


def _roman_urdu_contact_instruction(lead: Dict[str, Any]) -> str:
    if lead.get("phone"):
        return f"{lead['phone']} par call karein aur owner, manager ya marketing/customer enquiries handle karne wale shakhs se baat karne ko kahen."
    if lead.get("email"):
        return f"{lead['email']} ko email available hai; call se pehle Google Maps ya website se decision-maker ka public contact verify karein."
    if lead.get("website"):
        return "Website ka contact page aur Google Maps listing check karke public phone number ya decision-maker verify karein."
    return "Lead ke Google Maps verification link se public phone number verify karein. Kisi bhi unverified number par outreach na karein."


def build_outreach(lead: Dict[str, Any], service: str, reasons: List[str]) -> Dict[str, str]:
    name = lead.get("business_name", "the business")
    category = lead.get("category", "business")
    city = lead.get("city", "your city")
    issue = reasons[0] if reasons else "an opportunity to improve the digital customer journey"
    secondary = reasons[1] if len(reasons) > 1 else "the public customer journey can be made easier"
    value = SERVICE_VALUE.get(service, "a focused digital growth plan")
    instruction = _contact_instruction(lead)

    issue_ru = _roman_urdu_reason(issue)
    secondary_ru = _roman_urdu_reason(secondary)
    value_ru = ROMAN_URDU_SERVICE_VALUE.get(service, "ek focused digital growth plan jo customer journey aur enquiries ko improve kare")
    instruction_ru = _roman_urdu_contact_instruction(lead)

    # Only the cold-call script is Roman Urdu (Urdu written in Latin script).
    # WhatsApp, email, LinkedIn, call plan and follow-ups remain English below.
    cold_call = f"""CALL SE PEHLE
- {instruction_ru}
- Lead audit khol kar yeh observations confirm karein: {issue_ru}; {secondary_ru}.
- Maqsad: pehli call par poora project sell karna nahin, balkeh 15-minute audit review book karna hai.

SHURUAT
Aap: Assalam-o-Alaikum, kya meri baat {name} ke owner, manager, ya marketing aur customer enquiries handle karne wale person se ho sakti hai?

Jab decision-maker line par aa jaye:
Aap: Mera naam [Your Name] hai aur main [Agency Name] se baat kar raha/rahi hoon. Hum {city} mein {category.lower()} businesses ko customer enquiries aur follow-up improve karne mein help karte hain. Main ne {name} ki sirf public online presence review ki aur dekha ke {issue_ru}. Agar aap busy nahin hain to kya main 40 seconds mein call ki wajah explain kar sakta/sakti hoon?

40-SECOND REASON
Aap: Shukriya. Sab se clear opportunity yeh hai ke {issue_ru}. Hamari recommendation hai ke pehla step {service} ho. Is se {value_ru}. Maqsad yeh hai ke customer aap ko asani se find kare, trust kare aur phir call, WhatsApp ya booking tak pohanch sake.

DISCOVERY SAWALAT
1. Aap ke zyada tar naye customers aaj kal kahan se aate hain — referrals, Google, social media ya walk-ins?
2. Agar koi customer office hours ke baad call ya message kare to us enquiry ka follow-up kis tarah hota hai?
3. Kya aap har mahine milne wali enquiries ki quantity aur quality se satisfied hain?
4. Aap ki website, social pages aur WhatsApp follow-up abhi kaun manage karta hai?
5. Agle 30–60 din mein enquiries improve karna ya missed follow-ups kam karna aap ki priority hai?

TAILORED VALUE
Aap: Aap ne jo bataya us ke mutabiq sab se practical pehla step {service} hai. Hum pehle short audit karenge, phir highest-impact fixes agree karenge aur kisi bari commitment se pehle aap ko clear customer journey aur recommended plan dikhayenge.

CLOSE
Aap: Main {name} ke liye ek short audit prepare kar sakta/sakti hoon jis mein issues, recommended fixes, expected timeline aur options honge. Aap ke liye 15-minute call [Day/Time Option 1] behtar rahegi ya [Day/Time Option 2]?

AGAR PRICE POOCHAIN
Aap: Exact price scope par depend karti hai, is liye main bina details ke ghalat quote nahin dena chahta/chahti. 15-minute review ke baad hum sirf priority work ke mutabiq clear fixed option share kar denge. Proceed karna compulsory nahin hoga.

AGAR PEHLE SE KOI PROVIDER HAI
Aap: Yeh achi baat hai. Hum aap ko foran provider replace karne ko nahin keh rahe. Hamara audit second opinion ki tarah hoga aur {issue_ru} jaisi possible gaps verify karega. Agar sab kuch already covered hai to bhi findings aap ke paas rahengi.

AGAR BUSY HAIN
Aap: Bilkul samajh sakta/sakti hoon. Kya main do-line finding WhatsApp ya email par bhej doon aur phir aap ke convenient time par call kar loon?

AGAR INTERESTED NAHIN HAIN
Aap: Koi masla nahin. Record close karne se pehle sirf itna bata dein ke abhi priority nahin hai, ya yeh area already fully covered hai? Agar aap munasib samjhein to future mein ek follow-up ki permission le loon.

END
Aap: Aap ke waqt ka bohat shukriya. Main agreed summary abhi share kar deta/deti hoon aur agar meeting confirm hui hai to us ka time bhi confirm kar dunga/dungi. Allah Hafiz."""

    call_plan = f"""Primary objective: Book a 15-minute audit review for {service}.
Decision-maker: Owner, branch manager, marketing manager or operations manager.
Verified issue to lead with: {issue}.
Secondary discovery point: {secondary}.
Contact instruction: {instruction}
Next action after call: Record outcome, decision-maker name, objection, follow-up date and preferred channel in CRM."""

    objection_handling = f"""Too expensive: Offer a scoped first phase focused on the single highest-impact issue.
Send information: Confirm the correct WhatsApp/email and ask when to call after they review it.
Already working with someone: Position the audit as a second opinion, not a forced replacement.
No time: Ask for two available 15-minute windows and send the summary immediately.
Not interested: Ask one respectful reason, tag it in CRM, and stop outreach if they request no contact.
Need partner approval: Ask who else should join the audit review and schedule both people."""

    voicemail = (
        f"Assalam-o-Alaikum, this is [Your Name] from [Agency Name]. I reviewed the public online presence of {name} "
        f"and found a practical {service} opportunity related to {issue.lower()}. I will send a short message as well. "
        "You can call me back at [Your Number]. Thank you."
    )

    whatsapp = (
        f"Assalam-o-Alaikum. I’m [Your Name] from [Agency Name]. We reviewed the public online presence of {name} "
        f"and noticed {issue.lower()}. Our recommended first step is {service} to help improve customer enquiries and follow-up. "
        "May I send a one-page audit and arrange a 15-minute call?"
    )
    email = (
        f"Subject: Public digital audit for {name}\n\n"
        f"Assalam-o-Alaikum,\n\nWe reviewed the publicly available digital presence of {name} and identified {issue.lower()}. "
        f"A focused {service} plan could address this by delivering {value}.\n\n"
        "I can share a concise audit covering the findings, priority actions, timeline and suitable options. "
        "Would a 15-minute review this week be convenient?\n\nRegards,\n[Your Name]\n[Agency Name]\n[Phone]\n[Email]"
    )
    linkedin = (
        f"Hi, I reviewed {name}'s public digital presence and noticed {issue.lower()}. "
        f"We help {category.lower()} businesses with {service}. May I send a brief audit and recommended first steps?"
    )
    follow_up = (
        f"Assalam-o-Alaikum, following up on the audit note for {name}. The main opportunity was {issue.lower()}, "
        f"and the recommended first step was {service}. Would you prefer a short call on [Option 1] or [Option 2]?"
    )
    return {
        "cold_call": cold_call,
        "call_plan": call_plan,
        "objection_handling": objection_handling,
        "voicemail": voicemail,
        "whatsapp": whatsapp,
        "email": email,
        "linkedin": linkedin,
        "follow_up": follow_up,
    }
