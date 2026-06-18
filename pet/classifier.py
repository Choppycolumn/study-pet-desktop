from __future__ import annotations

from dataclasses import dataclass

from .monitor import ActivitySnapshot
from .settings import PetSettings


Category = str


@dataclass
class Classification:
    category: Category
    reason: str
    domain: str


class ActivityClassifier:
    def __init__(self, settings: PetSettings):
        self.settings = settings

    def classify(self, snapshot: ActivitySnapshot) -> Classification:
        title = snapshot.title.lower()
        process = snapshot.process_name.lower()
        domain = snapshot.domain.lower().removeprefix("www.")

        if domain:
            if self._domain_matches(domain, self.settings.study_domains):
                return Classification("study", "study domain", domain)
            if self._domain_matches(domain, self.settings.entertainment_domains):
                return Classification("entertainment", "entertainment domain", domain)
            if self._domain_matches(domain, self.settings.social_domains):
                return Classification("social", "social domain", domain)

        if process in self.settings.entertainment_processes or any(name in process for name in ["game", "steam"]):
            return Classification("entertainment", "entertainment process", domain)

        if process in self.settings.tool_processes:
            return Classification("tool", "tool process", domain)

        if self._contains_any(title, self.settings.entertainment_keywords):
            return Classification("entertainment", "entertainment keyword", domain)

        if self._contains_any(title, self.settings.study_keywords):
            if process in {"chrome.exe", "msedge.exe", "firefox.exe"} and domain:
                return Classification("study", "study keyword in browser title", domain)
            return Classification("study", "study keyword", domain)

        if process in {"chrome.exe", "msedge.exe", "firefox.exe"}:
            return Classification("unknown", "browser without matched domain", domain)

        if process:
            return Classification("tool", "active desktop app", domain)

        return Classification("unknown", "no active window", domain)

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        lowered_keywords = [item.lower() for item in keywords]
        return any(keyword and keyword in text for keyword in lowered_keywords)

    def _domain_matches(self, domain: str, rules: list[str]) -> bool:
        normalized = domain.lower().removeprefix("www.")
        return any(normalized == rule.lower().removeprefix("www.") or normalized.endswith(f".{rule.lower().removeprefix('www.')}") for rule in rules)
