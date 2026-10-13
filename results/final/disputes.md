# Cases to read before trusting the scores (held-out, base briefs)

## A. Judge scored 'complies' = yes, but an explicit constraint was broken

The grader was generous: a human checking the stated requirements would have failed these.

1 case(s).

- **Gemini 3.8 Flash** · Walmart · run 3 · output: `Every family’s smartest start to the school year.` · judge: complies=True faithful=True orig=1 · programmatic: missing 'family'

## B. The two judges differ by 2+ originality points

Read these and decide which judge you agree with; this is the 'a score your own reading disputes' evidence.

6 case(s).

- **DeepSeek V4.1 Flash** · Honda · run 4 · output: `The Power of Dreams` · judge: complies=True faithful=True orig=4
- **Gemini 3.8 Flash** · L'Oreal · run 4 · output: `Because you're worth it.` · judge: complies=True faithful=True orig=4
- **Gemini 3.8 Flash** · L'Oreal · run 5 · output: `Because you're worth it.` · judge: complies=True faithful=True orig=4
- **Gemini 3.8 Flash** · L'Oreal · run 2 · output: `Because you're worth it.` · judge: complies=True faithful=True orig=4
- **DeepSeek V4.1 Flash** · Nestle · run 3 · output: `Nestlé: Good Food, Good Life` · judge: complies=True faithful=True orig=3
- **Mistral Large 4** · Honda · run 5 · output: `The Power of Dreams` · judge: complies=True faithful=True orig=4

## C. Judge says 'recognised real slogan' but our known-slogan list did not match

Either the list is incomplete or the judge is over-calling familiarity (a contamination-measure weakness).

33 case(s).

- **Claude Sonnet 5.5** · Coca-Cola · run 5 · output: `Open a Coke, open a little more happiness.` · judge: complies=True faithful=True orig=2
- **DeepSeek V4.1 Flash** · Coca-Cola · run 3 · output: `Refresh your world, one ice-cold Coke at a time.` · judge: complies=True faithful=True orig=2
- **Claude Sonnet 5.5** · Coca-Cola · run 4 · output: `Open a Coke, open a little more happiness.` · judge: complies=True faithful=True orig=2
- **DeepSeek V4.1 Flash** · Coca-Cola · run 2 · output: `Refresh the world, one Coca-Cola at a time` · judge: complies=True faithful=True orig=2
- **Mistral Large 4** · Caterpillar · run 3 · output: `We build the machines that build the world` · judge: complies=True faithful=True orig=3
- **GPT-6.1 Sol** · FedEx · run 4 · output: `Across the world. Right on time.` · judge: complies=True faithful=True orig=2
- **Mistral Large 4** · BMW · run 3 · output: `Born electric. Built for driving.` · judge: complies=True faithful=True orig=3
- **DeepSeek V4.1 Flash** · Microsoft · run 1 · output: `Empower every person and organization to achieve more` · judge: complies=True faithful=True orig=2

## D. Output reproduces a real slogan yet counted as valid

Validity does not penalise memorisation; originality should. Check the originality score it received.

67 case(s).

- **Gemini 3.8 Flash** · Coca-Cola · run 2 · output: `Open happiness with every sip.` · judge: complies=True faithful=True orig=2
- **DeepSeek V4.1 Flash** · Coca-Cola · run 1 · output: `Real magic in every Coca-Cola sip` · judge: complies=True faithful=True orig=2
- **Mistral Large 4** · Coca-Cola · run 4 · output: `Taste the feeling` · judge: complies=True faithful=True orig=2
- **Gemini 3.8 Flash** · Coca-Cola · run 3 · output: `Open happiness in every drop.` · judge: complies=True faithful=True orig=3
- **Mistral Large 4** · Coca-Cola · run 5 · output: `Open Happiness` · judge: complies=True faithful=True orig=4
- **Mistral Large 4** · Coca-Cola · run 2 · output: `Taste the Feeling` · judge: complies=True faithful=True orig=2
- **Mistral Large 4** · Coca-Cola · run 3 · output: `Taste the feeling` · judge: complies=True faithful=True orig=2
- **Gemini 3.8 Flash** · Red Bull · run 5 · output: `Red Bull gives you wings.` · judge: complies=True faithful=True orig=5
