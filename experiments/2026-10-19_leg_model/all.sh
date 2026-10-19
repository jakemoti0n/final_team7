#!/usr/bin/env bash
H=$(cd "$(dirname "$0")" && pwd); R=~/limbo; D=$R/experiments/2026-10-14_social_people/worlds; W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
cp $D/zz_social_approach.sdf $D/zz_social_approach_movers.json $W/
for s in approach corr; do for i in 1 2; do for c in base cand; do $H/run.sh $c $s $i; done; done; done
rm -f $W/zz_social_approach.sdf $W/zz_social_approach_movers.json
git -C $R status --short; echo "=== 끝 $(date +%H:%M)"
