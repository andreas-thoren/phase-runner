## Before launch
- Before making repo public remove entire git history and start with a clean slate.
- Set up SMTP backend for password reset and email verification.

## Do later (not prioritized)
- Add export option for user data
- Maybe create some default periodization schemes that users can choose from when creating a new plan.
- Create reordering possibility for microcycles within mesocycles and mesocycles within macrocycle. This should be done with drag and drop.
- Create web page on github where you can try out the application. For the test site session should be used instead of proper database.

## Possible future optimizations
- Add denormalized end_date to Macrocycle. Will need to have some kind of hook whenever creaing/editing/deleting microcycle. Should also apply when microcycles are cascade deleted from mesocycle. Maybe also have some way to postpone calculation of end_date when mass creating microcycles (create_default_cycle).