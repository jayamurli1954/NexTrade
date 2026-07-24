# NexTrade Execution State Machine & Protection Lifecycle Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Locations:**  
* [execution/state_machine.py](file:///d:/Back_up/NexTrade/execution/state_machine.py) (`ExecutionStateMachine`)  
* [protection/lifecycle.py](file:///d:/Back_up/NexTrade/protection/lifecycle.py) (`ProtectionLifecycleManager`)  

---

## 1. Architectural Scope & Pipeline

Sub-Phase 3D introduces the **Execution State Machine** and **Protection Lifecycle Manager**.

It enforces valid order transition state graphs and evaluates market price ticks against active positions to emit `ProtectionDecision` objects and dispatch exit requests through `ExecutionGateway`.

$$\text{Risk} \neq \text{Authorization} \neq \text{Protection} \neq \text{Execution} \neq \text{Reconciliation}$$

---

## 2. Order Execution Transition State Graph

Order execution state follows strict unidirectional transitions:

$$\text{CREATED} \longrightarrow \text{AUTHORIZED} \longrightarrow \text{SUBMITTED} \longrightarrow \begin{cases} \text{PARTIALLY\_FILLED} \rightarrow \text{FILLED} \\ \text{FILLED} \\ \text{REJECTED} \\ \text{CANCELLED} \\ \text{EXPIRED} \\ \text{UNKNOWN} \quad (\text{Reconciliation Required}) \end{cases}$$

Attempting any invalid jump (e.g. `CREATED` $\rightarrow$ `FILLED` or `REJECTED` $\rightarrow$ `FILLED`) raises a `ValueError`.

---

## 3. Protection Lifecycle States & The 10 Mandatory Refinements

1. **No Direct Broker Bypass**: `ProtectionLifecycleManager` $\rightarrow$ `ProtectionDecision` $\rightarrow$ `ExecutionRequest` $\rightarrow$ `ExecutionGateway` $\rightarrow$ `BrokerAdapter`.
2. **Partial-Fill Position Sizing**: $Q_{protected} \le Q_{open\_position}$. Dynamic scale-in updates protected quantity.
3. **Deterministic SL/TP Precedence**: Ambiguous simultaneous SL/TP breach produces `AMBIGUOUS_PROTECTION_TRIGGER` $\rightarrow$ `RECONCILIATION_REQUIRED`.
4. **Trailing Activation Lifecycle**: Explicit progression from initial SL to Trailing Active.
5. **Trailing Distance vs Trailing Step Separation**: Trailing Distance is positioning offset (`ABSOLUTE` or `PERCENTAGE`), Trailing Step is update frequency threshold relative to `last_reference_price`.
6. **Explicit Protection States**: `INACTIVE`, `ACTIVE`, `EXIT_PENDING`, `CLOSED`, `CANCELLED`, `RECONCILIATION_REQUIRED`.
7. **UNKNOWN Exit Handling**: Exit returning `status == UNKNOWN` puts protection in `RECONCILIATION_REQUIRED`.
8. **Protection Idempotency**: `idempotency_key = f"PROTECTION_EXIT:{position_id}:{generation}:{trigger_reason}"`.
9. **Explicit Protection Trigger Reasons**: `STOP_LOSS`, `TAKE_PROFIT`, `TRAILING_STOP`, `AMBIGUOUS_PROTECTION_TRIGGER`.
10. **Restart State Recovery**: `to_dict()` and `from_dict()` methods for restart state serialization.
