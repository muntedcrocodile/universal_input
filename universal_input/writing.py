# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small, offline English writing rules. Ambiguous grammar stays a suggestion."""
from dataclasses import dataclass
import re


WORDS = re.compile(r"(?<!\w)[^\W\d_]+(?:['’][^\W\d_]+)*(?!\w)", re.UNICODE)

# Deliberately curated: never automatically accept the dictionary's first guess.
# Valid words such as cant, wont, were, well, hell and ill need context instead.
CORRECTIONS = {
    "im": "I'm", "ive": "I've", "i": "I", "i'm": "I'm", "i've": "I've",
    "i'll": "I'll", "i'd": "I'd", "dont": "don't", "doesnt": "doesn't",
    "didnt": "didn't", "isnt": "isn't", "arent": "aren't", "wasnt": "wasn't",
    "werent": "weren't", "hasnt": "hasn't", "havent": "haven't",
    "hadnt": "hadn't", "couldnt": "couldn't", "shouldnt": "shouldn't",
    "wouldnt": "wouldn't", "youre": "you're", "theyre": "they're",
    "youve": "you've", "weve": "we've", "theyve": "they've",
    "youll": "you'll", "theyll": "they'll", "thats": "that's",
    "whats": "what's", "heres": "here's", "theres": "there's",
    "teh": "the", "adn": "and", "hte": "the", "taht": "that",
    "thier": "their", "recieve": "receive", "recieved": "received",
    "definately": "definitely", "seperate": "separate", "becuase": "because",
}

# Base verbs which give a useful, narrow signal for the missing apostrophe.
# Excluding nouns like "will" and "health" avoids "ill will" / "ill health".
ILL_VERBS = (
    "be", "go", "do", "have", "get", "make", "take", "try", "send", "check",
    "see", "come", "call", "let", "help", "look", "tell", "give", "keep",
    "bring", "ask", "use", "need", "start", "finish", "work", "write",
    "read", "test", "fix", "put", "leave", "return", "meet", "wait", "pay",
)
ILL = re.compile(r"\b(ill)[ \t]+(?:" + "|".join(ILL_VERBS) + r")\b", re.IGNORECASE)
REPEATED = re.compile(r"\b(the|a|an|to|of|in|on|at|for|with|and|or|is|are|was|were|it|this)[ \t]+\1\b", re.IGNORECASE)
AGREEMENT = re.compile(r"\b(I|you|we|they|he|she|it)[ \t]+(am|is|are|was|were|has|have|does|do)\b", re.IGNORECASE)
VERBS = {
    "i": {"is": "am", "are": "am", "has": "have", "does": "do"},
    "you": {"am": "are", "is": "are", "was": "were", "has": "have", "does": "do"},
    "we": {"am": "are", "is": "are", "was": "were", "has": "have", "does": "do"},
    "they": {"am": "are", "is": "are", "was": "were", "has": "have", "does": "do"},
    "he": {"am": "is", "are": "is", "have": "has", "do": "does"},
    "she": {"am": "is", "are": "is", "have": "has", "do": "does"},
    "it": {"am": "is", "are": "is", "have": "has", "do": "does"},
}
# A small vocabulary avoids guessing pronunciation (e.g. a university, an hour).
VOWEL_SOUND = "apple|apples|orange|oranges|egg|eggs|elephant|idea|hour|honour|honor|honest|umbrella"
CONSONANT_SOUND = "book|car|cat|dog|house|user|university|unicorn|useful|European|one"
ARTICLE = re.compile(r"\b(a)[ \t]+(" + VOWEL_SOUND + r")\b|\b(an)[ \t]+(" + CONSONANT_SOUND + r")\b", re.IGNORECASE)
SENTENCE_END = re.compile(r"([.!?]+)[\"'’”\)\]]*[ \t\n]+[\"'‘“\(\[]*\Z")
ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
                 "e.g", "i.e", "approx", "no", "fig", "vol", "dept", "inc", "ltd", "a.m", "p.m"}


def starts_sentence(text, start):
    """Require explicit sentence punctuation; a field may start mid-sentence."""
    before = text[max(0, start - 128):start]
    ending = SENTENCE_END.search(before)
    if not ending:
        return False
    punctuation = ending.group(1)
    preceding = before[:ending.start()]
    if punctuation == ".":
        token = re.search(r"([\w.]+)\Z", preceding)
        if not token:
            return False
        word = token.group(1)
        # Titles, initials, dotted abbreviations and numbered list markers.
        if word.lower() in ABBREVIATIONS or "." in word or (len(word) == 1 and word.isupper()):
            return False
        if word.isdigit() and not preceding[:-len(word)].strip():
            return False
    elif punctuation == "...":
        return False
    return bool(preceding and preceding[-1] != "\0")


@dataclass(frozen=True)
class WritingIssue:
    start: int
    end: int
    replacement: str
    message: str
    kind: str = "grammar"
    automatic: bool = False
    trigger_end: int = 0


def match_case(word, replacement):
    if word.isupper() and len(word) > 1:
        return replacement.upper()
    if word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def writing_issues(text, grammar=True, capitalization=True):
    """Return code-point spans; masked non-prose must contain NULs, not spaces."""
    issues = []
    for match in WORDS.finditer(text):
        word = match.group()
        normalized = word.replace("’", "'")
        replacement = CORRECTIONS.get(normalized.lower())
        capitalise = capitalization and word[0].islower() and starts_sentence(text, match.start())
        if replacement is None and not capitalise:
            continue
        # Uppercase IM/IVE can be acronyms; uppercase typo/contraction fixes
        # otherwise preserve the user's casing.
        if word in ("IM", "IVE"):
            continue
        kind = "spelling" if replacement is not None else "grammar"
        replacement = match_case(word, replacement or word)
        if capitalise:
            replacement = replacement[0].upper() + replacement[1:]
        if "’" in word:
            replacement = replacement.replace("'", "’")
        if replacement != word:
            message = "Check this spelling or contraction."
            if normalized.lower() in ("i", "i'm", "i've", "i'll", "i'd"):
                message = "Capitalise the pronoun I."
            elif capitalise:
                message = "Start a new sentence with a capital letter."
            issues.append(WritingIssue(match.start(), match.end(), replacement,
                                       message, kind, True, match.end()))
    for match in ILL.finditer(text):
        # A preceding word often makes this the adjective: "the ill have…",
        # "feeling ill ...". Require a sentence/clause start or a conjunction.
        before = text[:match.start()].rstrip(" \t")
        if re.search(r"[\w’']\Z", before) and not re.search(r"\b(?:and|but|so|then|that)\Z", before, re.IGNORECASE):
            continue
        replacement = "I'LL" if match.group(1).isupper() else "I'll"
        issues = [issue for issue in issues if (issue.start, issue.end) != (match.start(1), match.end(1))]
        issues.append(WritingIssue(match.start(1), match.end(1), replacement,
                                   "Use I'll to mean I will.", "spelling", True, match.end()))
    if grammar:
        for match in REPEATED.finditer(text):
            replacement = match.group(1)
            if capitalization and starts_sentence(text, match.start()):
                replacement = replacement[0].upper() + replacement[1:]
            issues = [issue for issue in issues if not match.start() <= issue.start < match.end()]
            issues.append(WritingIssue(match.start(), match.end(), replacement, "Repeated word."))
        for match in AGREEMENT.finditer(text):
            subject, verb = match.group(1).lower(), match.group(2).lower()
            replacement = VERBS[subject].get(verb)
            if replacement:
                # "Does he have" and "Did he do" use the base form.
                before = text[:match.start()].rstrip(" \t")
                if verb in ("have", "do") and re.search(r"\b(?:does|doesn't|did|didn't)\Z", before, re.IGNORECASE):
                    continue
                issues.append(WritingIssue(match.start(2), match.end(2), match_case(match.group(2), replacement),
                                           "The verb should agree with its subject."))
        for match in ARTICLE.finditer(text):
            group = 1 if match.group(1) else 3
            replacement = "an" if group == 1 else "a"
            issues.append(WritingIssue(match.start(group), match.end(group), match_case(match.group(group), replacement),
                                       "Choose a or an for the following sound."))
    return sorted(issues, key=lambda issue: (issue.start, issue.end))
