# Changes of reorder view

## Visual changes

### Large screens
- Thin title row should sit between meso row and micro rows instead of on top of meso row as now. Thin top border should seperate from meso "row" above.

### Small screens
- No title row. 3 vals per micro. Start date, Type, Comment. Same visuals and stacking as for summary view on small screens for these fields. Do not show other info per micro on small screens.

### Both screen sizes
- Columns should come in same order as they do in summary view.
- Blue vertical line should only span microcycles (same as in summary view for small screens)

## Other changes
- Place here directly above and below selected microcycle should not be shown at all (display none?). After implementing this you should be able to remove some styling that is no longer necessary (maybe js as well dont remember) since those 2 fields are no longer shown at all and therefore no longer need to be visually differentiated from active place here fields. Same for focus hover effects. No longer needed if display=None.
