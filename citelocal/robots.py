"""A small, introspectable robots.txt parser.

`urllib.robotparser` can answer "may I fetch this URL", but an audit needs to
explain *why* a bot is blocked and *which rule* did it. So we parse groups
ourselves and keep the matching rule around for the report.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Rule:
    allow: bool
    path: str
    line_number: int

    @property
    def directive(self) -> str:
        return "Allow" if self.allow else "Disallow"


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: str | None = None


@dataclass
class Decision:
    allowed: bool
    matched_agent: str | None  # which user-agent group applied
    matched_rule: Rule | None  # which rule decided it
    explicit: bool  # True when a group named this bot directly

    @property
    def reason(self) -> str:
        if self.matched_rule is None:
            scope = f"'{self.matched_agent}'" if self.matched_agent else "no group"
            return f"no matching rule ({scope}) — allowed by default"
        rule = self.matched_rule
        agent = self.matched_agent or "*"
        return (
            f"{rule.directive}: {rule.path or '(empty)'} "
            f"under User-agent: {agent} (line {rule.line_number})"
        )


class RobotsFile:
    """Parsed robots.txt.

    `missing=True` means we could not retrieve a robots.txt, which per the
    standard means everything is permitted.
    """

    def __init__(self, text: str = "", missing: bool = False) -> None:
        self.raw = text
        self.missing = missing
        self.groups: list[Group] = []
        self.sitemaps: list[str] = []
        self._parse(text)

    def _parse(self, text: str) -> None:
        current: Group | None = None
        # True while we are still reading stacked User-agent lines for a group.
        collecting_agents = False

        for number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            if ":" not in line:
                continue

            field_name, _, value = line.partition(":")
            field_name = field_name.strip().lower()
            value = value.strip()

            if field_name == "user-agent":
                # A User-agent line after rules have started opens a new group.
                if current is None or not collecting_agents:
                    current = Group()
                    self.groups.append(current)
                    collecting_agents = True
                current.agents.append(value.lower())
            elif field_name in ("allow", "disallow"):
                if current is None:
                    # Rules before any User-agent line: treat as a '*' group so
                    # they are not silently discarded.
                    current = Group(agents=["*"])
                    self.groups.append(current)
                collecting_agents = False
                current.rules.append(
                    Rule(allow=(field_name == "allow"), path=value, line_number=number)
                )
            elif field_name == "crawl-delay":
                if current is not None:
                    collecting_agents = False
                    current.crawl_delay = value
            elif field_name == "sitemap":
                self.sitemaps.append(value)

    def group_for(self, agent_token: str) -> tuple[Group | None, str | None, bool]:
        """Find the group governing `agent_token`.

        Returns (group, matched_agent_name, was_explicit). Exact name matches
        win over '*', matching how crawlers resolve groups.
        """
        token = agent_token.lower()

        for group in self.groups:
            for agent in group.agents:
                if agent == token:
                    return group, agent_token, True

        # Substring match: a robots.txt saying "GPTBot" should also govern a
        # request from "GPTBot/1.1". Longest declared agent wins.
        best: tuple[Group, str] | None = None
        for group in self.groups:
            for agent in group.agents:
                if agent and agent != "*" and (agent in token or token in agent):
                    if best is None or len(agent) > len(best[1]):
                        best = (group, agent)
        if best is not None:
            return best[0], best[1], True

        for group in self.groups:
            if "*" in group.agents:
                return group, "*", False

        return None, None, False

    def check(self, agent_token: str, path: str = "/") -> Decision:
        group, matched_agent, explicit = self.group_for(agent_token)

        if self.missing or group is None:
            return Decision(True, matched_agent, None, explicit)

        # Longest-prefix match wins; Allow beats Disallow at equal length.
        best: Rule | None = None
        for rule in group.rules:
            if not rule.path:
                # "Disallow:" with no value means allow everything; it never
                # matches as a prefix rule.
                continue
            if _path_matches(rule.path, path):
                if (
                    best is None
                    or len(rule.path) > len(best.path)
                    or (len(rule.path) == len(best.path) and rule.allow and not best.allow)
                ):
                    best = rule

        if best is None:
            return Decision(True, matched_agent, None, explicit)
        return Decision(best.allow, matched_agent, best, explicit)


def _path_matches(pattern: str, path: str) -> bool:
    """Prefix match with the de-facto '*' and '$' wildcard extensions."""
    if "*" not in pattern and "$" not in pattern:
        return path.startswith(pattern)

    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]

    segments = pattern.split("*")
    position = 0
    for index, segment in enumerate(segments):
        if not segment:
            continue
        if index == 0:
            if not path.startswith(segment):
                return False
            position = len(segment)
            continue
        found = path.find(segment, position)
        if found == -1:
            return False
        position = found + len(segment)

    if anchored:
        return position == len(path) if segments[-1] else True
    return True
