---
error: true
---

{
  "ok": false,
  "error": {
    "code": "CONFIRMATION_REQUIRED",
    "message": "invoice_mail: czynnosc nieodwracalna wymaga potwierdzenia",
    "hint": "Pokaz podsumowanie userowi i powtorz z confirm=<token> po jego zgodzie.",
    "retryable": false,
    "details": {
      "action": "invoice_mail",
      "token": "1a2b3c4d5e6f",
      "summary": {
        "invoice": "{{input.number}}",
        "to": "ksiegowosc@firma-abc.pl",
        "gross": "14760.00",
        "attachment": "A1_11_2026.pdf"
      }
    }
  }
}
