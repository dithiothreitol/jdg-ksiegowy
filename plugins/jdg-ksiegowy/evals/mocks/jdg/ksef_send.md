---
error: true
---

{
  "ok": false,
  "error": {
    "code": "CONFIRMATION_REQUIRED",
    "message": "ksef_send: czynnosc nieodwracalna wymaga potwierdzenia",
    "hint": "Pokaz podsumowanie userowi i powtorz z confirm=<token> po jego zgodzie.",
    "retryable": false,
    "details": {
      "action": "ksef_send",
      "token": "1a2b3c4d5e6f",
      "summary": {
        "env": "prod",
        "invoice": "{{input.number}}",
        "buyer": "Firma ABC Sp. z o.o.",
        "net": "12000.00",
        "vat": "2760.00",
        "gross": "14760.00"
      }
    }
  }
}
