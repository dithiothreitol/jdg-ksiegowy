"""PreToolUse: faze wykonania czynnosci nieodwracalnej zatwierdza czlowiek, nie model.

Narzedzia `ksef_send`, `invoice_mail`, `jpk_submit` (i `jdg ... --confirm` w Bash) wymagaja
tokenu z podsumowania. Token widzi tez model, wiec wywolanie z tokenem zawsze przechodzi
przez okno zgody Claude Code (`permissionDecision: ask`) — rowniez w trybie auto.
Bez tokenu (faza podgladu) hook nic nie robi. Tylko biblioteka standardowa.
"""

import json
import re
import sys

JDG_CONFIRM = re.compile(r"\bjdg\b.*\s--confirm\b")


def decision(event: dict) -> dict | None:
    tool = event.get("tool_name", "")
    args = event.get("tool_input") or {}
    if tool == "Bash":
        command = args.get("command", "")
        target = command if JDG_CONFIRM.search(command) else None
    else:
        target = f"{tool.rsplit('__', 1)[-1]} {json.dumps(args, ensure_ascii=False)}"
        target = target if args.get("confirm") else None
    if target is None:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "jdg: czynnosc nieodwracalna (KSeF / urzad skarbowy / e-mail do klienta). "
                f"Zatwierdz tylko, jesli widziales podsumowanie i sie zgadzasz: {target}"
            ),
        }
    }


if __name__ == "__main__":
    result = decision(json.load(sys.stdin))
    if result is not None:
        print(json.dumps(result, ensure_ascii=False))
