## TODO:s
- Add favicon
- Add option for users to change password, email and other account settings.
- Add export option for user data
- Improve visuals for small screens. Especially important for summary view. Maybe split form horizonally planned to left and actual executed to the right.
- What should be shown regarding workouts in summary view? Only executed workouts or all. Dropdown filter for this?
- Create API for uploading workouts from cli.
- Change periodization models so that they are not specifically tied to running. Any aerobic sport should work. This will also require naming changes for some table headings and fields.
User should be able to choose primary sport when creating a new plan, and then the periodization model will be based on that. For example, if the user chooses cycling, then the periodization model will be based on cycling training principles instead of running.

## Possible future features
- Add media file support (MEDIA_URL, MEDIA_ROOT, Dokku bind mount) for user-uploaded content.
- Maybe support triathlon periodization models in the future. Will require large changes so needs to be carefully planned if implemented.
- Maybe create some default periodization schemes that users can choose from when creating a new plan.
- Create reordering possibility for microcycles within mesocycles and mesocycles within macrocycle. This should be done with drag and drop.
- Create web page on github where you can try out the application. For the test site session should be used instead of proper database.

## Possible future optimizations
- Add denormalized end_date to Macrocycle. Will need to have some kind of hook whenever creaing/editing/deleting microcycle. Should also apply when microcycles are cascade deleted from mesocycle. Maybe also have some way to postpone calculation of end_date when mass creating microcycles (create_default_cycle).