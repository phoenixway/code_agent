Оцінка: **ще ~25–45 умовних годин** до “достатньо мігровано на compiler path”, але **не до повного видалення legacy**.

Я б розділив так:

```text
A. Завершити structural protocol authority
   ~6–10 год

B. Runtime integration / smoke / edge cases
   ~6–10 год

C. ACTION_ONLY / INTENT_ACTION_BUNDLE boundary hardening
   ~5–8 год

D. PLAINTEXT_ONLY / final answer boundary audit
   ~5–10 год

E. Cleanup, docs, consistency, regression hardening
   ~3–7 год
```

## Що лишилось найближче

Після `E_INTENT_COMPLETE_WITH_ACTION` ще буде кілька точкових compiler candidates:

```text
1. complete intent + action
2. complete intent + multiple controls / visible text edge cases
3. intent + file_content pairing edge cases
4. bundle + file_content correctness
5. maybe nested/malformed intent payload diagnostics
```

Це ще **~1–2 робочі сесії** у твоєму поточному темпі.

## Найбільший невирішений шматок

Справжня “міграція на compiler path” впирається не в structural errors, а в policy-heavy зони:

```text
PLAINTEXT_ONLY
ACTION_ONLY
valid INTENT_ACTION_BUNDLE
final answer / evidence sufficiency
ActionPolicy
subgoal validation
search narrowing
```

Там compiler не може просто сказати “valid => dispatch/stop”, бо це вже не syntax/protocol, а runtime policy.

Тому realistic target:

```text
compiler authoritative for protocol structure ✅
legacy/runtime authoritative for policy ✅
```

а не:

```text
compiler replaces everything ❌
```

## Мій прогноз

Якщо продовжувати нинішнім обережним стилем:

```text
до solid compiler-structural authority:
~10–15 год

до compiler-first response protocol with legacy fallback:
~25–45 год

до повного видалення legacy semantic path:
60+ год, і я б не радив зараз
```

## Практичний критерій “міграцію можна зупинити”

Я б зупинився, коли виконано:

```text
1. всі precise structural diagnostics у bridge
2. broad E_MIXED_VISIBLE_TEXT_AND_CONTROL лишається legacy
3. ACTION_ONLY не bypass-ить ActionPolicy
4. PLAINTEXT_ONLY не bypass-ить sufficiency/final-answer policy
5. shadow tests показують тільки documented mismatches
6. runtime smoke не показує dispatch для invalid compiler cases
```

Після цього compiler path буде достатньо зрілий, навіть якщо legacy ще існує як policy/fallback.
