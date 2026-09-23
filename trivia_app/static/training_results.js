(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.PointsTrainingResults = factory();
})(typeof window !== 'undefined' ? window : this, function () {
    const names = {win_rate:'Win rate',loss_rate:'Loss rate',draw_rate:'Draw rate',total_wins:'Wins',
        total_goals:'Goals scored',goals_conceded:'Goals conceded',goals_per_game:'Goals per match',
        points_per_game:'Points per match',clean_sheets:'Clean sheets',kit_colour:'Kit shirt colour',historical_weather:'Historical weather',unsupported:'Unsupported phrase',ambiguous:'Ambiguous phrase'};
    const label = value => names[value] || value || 'No match';
    function probe(data) {
        let heading = data.label ? `Model suggests: ${label(data.label)}` : 'No usable prediction';
        let assessment = 'Metric classification only. No team, season or match result has been calculated.';
        if (!data.label) assessment = 'No character features from this input occur in the model vocabulary.';
        else if (data.rule_label && !data.trained_labels.includes(data.rule_label)) {
            heading = 'Not trained for this metric';
            assessment = `The exact-match rules recognize ${label(data.rule_label)}, but this model has no such class. Its suggestion is not a supported interpretation.`;
        } else if (data.rule_label && data.rule_label !== data.label) {
            heading = 'Rules and model disagree';
            assessment = `Exact-match rules: ${label(data.rule_label)}. Model: ${label(data.label)}. No query was executed.`;
        }
        return {heading,assessment,seen:data.seen_in_training ? 'This phrase was used in training; this is not an independent test.' : 'This exact phrase was not used in training.',
            scores:Object.entries(data.scores_uncalibrated || {}).sort((a,b)=>b[1]-a[1])};
    }
    function tally(model,split) {
        const rows = model.evaluation_examples?.[split] || [];
        return {correct:rows.filter(r=>r.expected===r.predicted).length,total:rows.length};
    }
    return {label,probe,tally};
});
