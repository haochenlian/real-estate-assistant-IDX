# MLS Schema Field Reference

Two tables live in the `idx_exchange` MySQL database. `california_sold` uses
RESO-standard names; `rets_property` uses IDX's own legacy naming for its core search
fields.

## rets_property — Active Listings

This table holds active California property listings currently for sale. Its core search
fields use IDX legacy names that do not appear in RESO or Trestle documentation.

| Column | Meaning |
|--------|---------|
| `L_ListingID` | MLS system listing ID; joins to `california_sold.ListingKey` |
| `L_DisplayId` | Human-readable MLS number shown on portals |
| `L_Address` | Full street address |
| `L_City` | City |
| `L_Zip` | Postal code |
| `L_Class` | Property class: Residential, CommercialSale, Land |
| `L_Type_` | Property subtype: SingleFamilyResidence, Condominium, Townhouse |
| `L_Keyword2` | Total bedrooms |
| `LM_Dec_3` | Total bathrooms, supports half-baths such as 2.5 |
| `L_SystemPrice` | Current list price used for search and display |
| `LM_Int2_3` | Approximate finished square footage |
| `L_Keyword1` | Lot size |
| `LMD_MP_Latitude` | Geographic latitude |
| `LMD_MP_Longitude` | Geographic longitude |
| `L_Status` | Listing status: Active, Pending, Withdrawn |
| `L_Remarks` | Full listing description text |
| `L_Photos` | JSON array of listing photo URLs |
| `YearBuilt` | Year the property was constructed |
| `AssociationFee` | Monthly HOA fee in dollars |
| `DaysOnMarket` | Days on market at time of data pull |
| `PoolPrivateYN` | Whether a private pool is present |
| `ViewYN` | Whether the property has a notable view |
| `FireplaceYN` | Whether a fireplace is present |
| `PhotoCount` | Number of listing photos available |
| `LA1_UserFirstName` | Listing agent first name |
| `LA1_UserLastName` | Listing agent last name |
| `LO1_OrganizationName` | Listing office or brokerage name |

## california_sold — Sold Transactions

This table holds sold, leased, and closed California transactions. Its columns follow
RESO-standard naming.

| Column | Meaning |
|--------|---------|
| `ListingKey` | Unique listing identifier; joins to `rets_property.L_ListingID` |
| `ClosePrice` | Final sale price |
| `CloseDate` | Date the transaction closed, stored as YYYY-MM-DD |
| `OriginalListPrice` | Original asking price when first listed |
| `ListPrice` | List price at time of contract |
| `DaysOnMarket` | Days from listing to contract |
| `PropertyType` | Residential, Land, ResidentialLease, CommercialSale |
| `PropertySubType` | SingleFamilyResidence, Condominium, Duplex |
| `LivingArea` | Finished living area in square feet |
| `LotSizeAcres` | Lot size in acres |
| `LotSizeSquareFeet` | Lot size in square feet |
| `BedroomsTotal` | Number of bedrooms |
| `BathroomsTotalInteger` | Number of bathrooms |
| `YearBuilt` | Year the property was built |
| `City` | City of the property |
| `PostalCode` | ZIP code |
| `Latitude` | Geographic latitude |
| `Longitude` | Geographic longitude |
| `UnparsedAddress` | Full street address |
| `ListAgentFullName` | Listing agent full name |
| `ListOfficeName` | Listing brokerage name |
| `BuyerOfficeName` | Buyer brokerage name |
| `PoolPrivateYN` | Whether a private pool is present |
| `ViewYN` | Whether the property has a view |
| `GarageSpaces` | Number of garage spaces |
| `AssociationFee` | Monthly HOA fee |
| `SubdivisionName` | Subdivision or community name |
| `HighSchoolDistrict` | School district name |

## Joining the two tables

To correlate an active listing with its sold history, join
`rets_property.L_ListingID` to `california_sold.ListingKey`. For market-level analysis,
match on city and postal code instead.
