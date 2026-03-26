## TODO:s
- Create API for uploading workouts from cli.
- Add export option for user data
- Maybe create some default periodization schemes that users can choose from when creating a new plan.
- Create reordering possibility for microcycles within mesocycles and mesocycles within macrocycle. This should be done with drag and drop.
- Create web page on github where you can try out the application. For the test site session should be used instead of proper database.

## Possible future features
- Add media file support (MEDIA_URL, MEDIA_ROOT, Dokku bind mount) for user-uploaded content.

## Possible future optimizations
- Add denormalized end_date to Macrocycle. Will need to have some kind of hook whenever creaing/editing/deleting microcycle. Should also apply when microcycles are cascade deleted from mesocycle. Maybe also have some way to postpone calculation of end_date when mass creating microcycles (create_default_cycle).