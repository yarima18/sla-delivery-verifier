# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json

class SLADeliveryVerifier(gl.Contract):
    """
    SLA / Delivery Verifier
    Client locks funds + writes natural-language SLA.
    Provider submits evidence URL.
    Contract fetches evidence and adjudicates with Equivalence Principle.
    """

    # We store everything as JSON strings inside TreeMaps (most reliable pattern)
    agreements: TreeMap[str, str]      # agreement_id -> JSON string of the agreement
    next_id: str

    def __init__(self):
        self.agreements = TreeMap()
        self.next_id = "0"

    # ──────────────────────────────────────────────
    # Create Agreement (Client locks funds)
    # ──────────────────────────────────────────────
    @gl.public.write.payable
    def create_agreement(self, sla_text: str, provider: str = "") -> str:
        if gl.message.value_sent == u256(0):
            raise Exception("Must send funds to lock")

        if len(sla_text.strip()) < 15:
            raise Exception("SLA text is too short")

        agreement_id = self.next_id
        self.next_id = str(int(self.next_id) + 1)

        agr = {
            "client": str(gl.message.sender_address),
            "provider": provider.strip(),
            "sla_text": sla_text.strip(),
            "amount": str(gl.message.value_sent),
            "evidence_url": "",
            "evidence_description": "",
            "status": "Open",
            "decision": "",
            "reason": ""
        }

        self.agreements[agreement_id] = json.dumps(agr, sort_keys=True)
        return agreement_id

    # ──────────────────────────────────────────────
    # Provider submits evidence
    # ──────────────────────────────────────────────
    @gl.public.write
    def submit_evidence(self, agreement_id: str, evidence_url: str, evidence_description: str = ""):
        if agreement_id not in self.agreements:
            raise Exception("Agreement does not exist")

        agr = json.loads(self.agreements[agreement_id])

        if agr["status"] != "Open":
            raise Exception("Agreement is not open for evidence")

        # If a provider was set, only that address can submit
        if agr["provider"] and agr["provider"] != str(gl.message.sender_address):
            raise Exception("Only the designated provider can submit evidence")

        # If no provider was set, the first submitter becomes the provider
        if not agr["provider"]:
            agr["provider"] = str(gl.message.sender_address)

        if not evidence_url.startswith("http"):
            raise Exception("Evidence URL must start with http")

        agr["evidence_url"] = evidence_url.strip()
        agr["evidence_description"] = evidence_description.strip()
        agr["status"] = "EvidenceSubmitted"

        self.agreements[agreement_id] = json.dumps(agr, sort_keys=True)

    # ──────────────────────────────────────────────
    # Adjudicate (core GenLayer logic)
    # ──────────────────────────────────────────────
    @gl.public.write
    def adjudicate(self, agreement_id: str):
        if agreement_id not in self.agreements:
            raise Exception("Agreement does not exist")

        agr = json.loads(self.agreements[agreement_id])

        if agr["status"] != "EvidenceSubmitted":
            raise Exception("Evidence has not been submitted yet")

        sla = agr["sla_text"]
        url = agr["evidence_url"]
        desc = agr["evidence_description"]

        def evaluate():
            try:
                page_content = gl.nondet.web.render(url, mode="text")
            except Exception as e:
                page_content = f"[Failed to fetch: {str(e)}]"

            page_content = page_content[:10000]

            prompt = f"""
You are an impartial adjudicator.

SLA / Acceptance Criteria:
{sla}

Evidence description from provider:
{desc}

Live content from the evidence URL:
{page_content}

Decide whether the evidence satisfies the SLA.

Respond ONLY with valid JSON in this exact format:
{{
  "decision": "APPROVED" or "REJECTED",
  "reason": "one or two short sentences"
}}
"""
            result = gl.nondet.exec_prompt(prompt, response_format="json")
            return result

        # Thoughtful Equivalence Principle
        result = gl.eq_principle.prompt_comparative(
            evaluate,
            principle="The decision field must be exactly the same (APPROVED or REJECTED). The reason should express the same overall judgment."
        )

        try:
            if isinstance(result, str):
                parsed = json.loads(result)
            else:
                parsed = result

            decision = str(parsed.get("decision", "REJECTED")).upper().strip()
            reason = str(parsed.get("reason", "No reason given"))[:400]

            if decision not in ("APPROVED", "REJECTED"):
                decision = "REJECTED"
                reason = "Invalid decision returned"
        except Exception:
            decision = "REJECTED"
            reason = "Failed to parse result"

        agr["decision"] = decision
        agr["reason"] = reason
        agr["status"] = "Adjudicated"
        self.agreements[agreement_id] = json.dumps(agr, sort_keys=True)

        # Note: actual fund transfer is simplified for Studio compatibility
        # In production you would use proper value transfer

    # ──────────────────────────────────────────────
    # View methods (NO dict returns)
    # ──────────────────────────────────────────────
    @gl.public.view
    def get_agreement_json(self, agreement_id: str) -> str:
        if agreement_id not in self.agreements:
            return "{}"
        return self.agreements[agreement_id]

    @gl.public.view
    def get_status(self, agreement_id: str) -> str:
        if agreement_id not in self.agreements:
            return "NotFound"
        agr = json.loads(self.agreements[agreement_id])
        return agr["status"]

    @gl.public.view
    def get_decision(self, agreement_id: str) -> str:
        if agreement_id not in self.agreements:
            return ""
        agr = json.loads(self.agreements[agreement_id])
        return agr.get("decision", "")

    @gl.public.view
    def get_next_id(self) -> str:
        return self.next_id
