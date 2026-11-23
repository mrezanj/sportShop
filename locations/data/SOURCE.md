
# Iranian Provinces and Cities Dataset

## Dataset information

- Dataset year: 1404
- Dataset file: `iran_divisions_1404_core.json`
- Imported record types:
  - Type 1: Provinces
  - Type 5: Cities
- Imported records:
  - 31 provinces
  - 1,481 cities

Urban zones (type 7), counties, districts, and villages are not imported as independent cities.

## Original source

- Repository: https://github.com/Hameds/IranCountryDivisions
- Dataset path: `packages/npm/data/1404/core.json`
- License: MIT
- License file: `LICENSE-IranCountryDivisions.txt`

The source repository describes its annual administrative-division data
as being based on the geographical divisions published by the
Statistical Center of Iran.

This project uses the repository's redistributed dataset. It does not
claim to be an official publication or direct distribution by the
Statistical Center of Iran.

## Attribution and license

The original dataset is distributed under the MIT License.

The accompanying `LICENSE-IranCountryDivisions.txt` file contains
the applicable license text.

The source repository and its authors retain their original rights.
This project includes the dataset under the terms of that license.

## Import behavior

The Django management command is:

`python manage.py import_iran_cities`

The import command:

- Maps source provinces to the existing `orders.PROVINCE_CHOICES`.
- Uses source province codes and city codes.
- Imports only type 1 and type 5 records.
- Resolves each city's province, county, and district through
  the source parent hierarchy.
- Uses update-or-create behavior and does not delete existing records.

Source record IDs are not used as permanent identifiers because
they may change between annual dataset versions.
