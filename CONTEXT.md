# Survey Flow

How a crowdsourcing survey is defined and how a respondent is walked through it. A survey is a directed graph of routes; the chatbot walks one question at a time and branches based on prior answers.

## Language

### Structure

**Survey**:
A complete, versioned questionnaire. Holds a pool of questions, a set of routes, and a pointer to where walking begins.
_Avoid_: Form, questionnaire, flow

**Question**:
A single prompt shown to the respondent, with its answer options. Belongs to the shared question pool and is referenced by routes by id.
_Avoid_: Step, prompt, item

**Route**:
A named node in the survey graph: an ordered list of questions that flow one after another *without branching*, plus a single exit decision. Routes are peers — none is "main" or "sub".
_Avoid_: Section, phase, flow, sub-route, main route

**Onstart**:
The id of the route where walking begins. The survey's single entry point. Replaces any notion of a privileged "main" route.
_Avoid_: Start route, main, root

### Branching

**Orchestrator**:
A route's exit decision — the logic that picks which route comes next when the current route's questions are exhausted. Expressed as the route's `next`, holding a list of `conditions` plus a `default`.
_Avoid_: Dispatcher, router, fork

**Condition**:
One ordered entry in an orchestrator's `conditions` list: a `when` clause paired with a `goto` target. Conditions are evaluated top to bottom; the first whose `when` matches wins.
_Avoid_: Rule, branch, case

**When**:
A rule's condition — a set of field→value checks that must *all* hold (logical AND) for the rule to match.
_Avoid_: Condition, predicate, guard

**Goto**:
A rule's target: the id of the next route to walk. A route id only — there is no jump to an individual question.
_Avoid_: Jump, next, link

**Default**:
The orchestrator's fallback when no rule matches. `null` means the survey ends here.
_Avoid_: Else, fallback route

**Merge**:
The convergence of several routes onto a shared downstream route, expressed as those routes' exits all pointing at the same target. The graph's way of "returning to the common path" — there is no call-and-return stack.
_Avoid_: Return, join, rejoin
