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


def build_outreach(lead: Dict[str, Any], service: str, reasons: List[str]) -> Dict[str, str]:
    name = lead.get("business_name", "the business")
    category = lead.get("category", "business")
    city = lead.get("city", "your city")
    issue = reasons[0] if reasons else "an opportunity to improve the digital customer journey"
    secondary = reasons[1] if len(reasons) > 1 else "the public customer journey can be made easier"
    value = SERVICE_VALUE.get(service, "a focused digital growth plan")
    instruction = _contact_instruction(lead)

    cold_call = f"""PRE-CALL
- {instruction}
- Open the lead audit and confirm these observations: {issue}; {secondary}.
- Goal: book a 15-minute audit review, not sell the full project on the first call.

OPENING
You: Assalam-o-Alaikum, may I speak with the owner, manager, or the person who handles marketing and customer enquiries for {name}?

Decision-maker joins:
You: My name is [Your Name] from [Agency Name]. We help {category.lower()} businesses in {city} improve enquiries and follow-up. I reviewed only the public online presence of {name} and noticed {issue.lower()}. Is this a bad time, or may I take 40 seconds to explain why I called?

40-SECOND REASON
You: Thank you. The main opportunity is {issue.lower()}. We would recommend starting with {service}: {value}. The objective is to make it easier for a customer to discover you, trust you and contact or book with you.

DISCOVERY QUESTIONS
1. How do most new customers currently find you: referrals, Google, social media or walk-ins?
2. When a customer calls or messages after working hours, how is that enquiry followed up?
3. Are you satisfied with the number and quality of enquiries you receive each month?
4. Who currently manages your website, social pages and WhatsApp follow-up?
5. Is improving enquiries or reducing missed follow-ups a priority in the next 30–60 days?

TAILORED VALUE
You: Based on what you shared, the first practical step is {service}. We would begin with a short audit, agree on the highest-impact fixes, and show the expected customer journey before any larger commitment.

CLOSE
You: I can prepare a concise audit for {name} with the issues, recommended fixes, timeline and options. Would a 15-minute call on [Day/Time Option 1] or [Day/Time Option 2] be easier?

IF THEY ASK FOR PRICE
You: The price depends on the exact scope, so I do not want to quote inaccurately. After the 15-minute review, we can give a fixed option based on the priority work only. There is no obligation to proceed.

IF THEY ALREADY HAVE A PROVIDER
You: That is good. We are not asking you to replace anyone immediately. The audit can act as a second opinion and identify gaps such as {issue.lower()}. If everything is already covered, you still keep the findings.

IF THEY ARE BUSY
You: Understood. May I send the two-line finding by WhatsApp or email, then call at a time you choose?

IF THEY ARE NOT INTERESTED
You: No problem. Before I close the record, is it because this is not a priority now, or because you already have the area fully covered? [Record the reason and ask permission for one future follow-up if appropriate.]

END
You: Thank you for your time. I will send the agreed summary now and confirm the meeting. Have a good day."""

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
