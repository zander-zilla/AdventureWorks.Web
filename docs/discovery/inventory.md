# Schema inventory – AdventureWorks2022 (OLTP) and AdventureWorksDW2022

Generated from the live before-stack databases by `scripts/discovery/generate.sh` (`inventory.sql` → `render.py`). Machine-readable form: [`schema.json`](schema.json). Do not edit by hand.

## Headline numbers

| Database | Schemas | Tables | Columns | Rows | PKs | FKs | Indexes | Views | Procs | Functions | Triggers |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AdventureWorks2022 | 6 | 71 | 486 | 760,837 | 71 | 90 | 173 | 20 | 10 | 11 | 11 |
| AdventureWorksDW2022 | 1 | 30 | 354 | 1,060,811 | 27 | 44 | 37 | 5 | 0 | 3 | 1 |

## AdventureWorks2022

### Tables per schema

| Schema | Tables | Rows | Tables (rows) |
|---|---|---|---|
| HumanResources | 6 | 934 | Department (16), Employee (290), EmployeeDepartmentHistory (296), EmployeePayHistory (316), JobCandidate (13), Shift (3) |
| Person | 13 | 141,250 | Address (19,614), AddressType (6), BusinessEntity (20,777), BusinessEntityAddress (19,614), BusinessEntityContact (909), ContactType (20), CountryRegion (238), EmailAddress (19,972), Password (19,972), Person (19,972), PersonPhone (19,972), PhoneNumberType (3), StateProvince (181) |
| Production | 25 | 349,895 | BillOfMaterials (2,679), Culture (8), Document (13), Illustration (5), Location (14), Product (504), ProductCategory (4), ProductCostHistory (395), ProductDescription (762), ProductDocument (32), ProductInventory (1,069), ProductListPriceHistory (395), ProductModel (128), ProductModelIllustration (7), ProductModelProductDescriptionCulture (762), ProductPhoto (101), ProductProductPhoto (504), ProductReview (4), ProductSubcategory (37), ScrapReason (16), TransactionHistory (113,443), TransactionHistoryArchive (89,253), UnitMeasure (38), WorkOrder (72,591), WorkOrderRouting (67,131) |
| Purchasing | 5 | 13,426 | ProductVendor (460), PurchaseOrderDetail (8,845), PurchaseOrderHeader (4,012), ShipMethod (5), Vendor (104) |
| Sales | 19 | 253,735 | CountryRegionCurrency (109), CreditCard (19,118), Currency (105), CurrencyRate (13,532), Customer (19,820), PersonCreditCard (19,118), SalesOrderDetail (121,317), SalesOrderHeader (31,465), SalesOrderHeaderSalesReason (27,647), SalesPerson (17), SalesPersonQuotaHistory (163), SalesReason (10), SalesTaxRate (29), SalesTerritory (10), SalesTerritoryHistory (17), ShoppingCartItem (3), SpecialOffer (16), SpecialOfferProduct (538), Store (701) |
| dbo | 3 | 1,597 | AWBuildVersion (1), DatabaseLog (1,596), ErrorLog (0) |

### Views (20)

| Name | Type | References |
|---|---|---|
| HumanResources.vEmployee | VIEW | HumanResources.Employee, Person.Address, Person.BusinessEntityAddress, Person.CountryRegion, Person.EmailAddress, Person.Person, Person.PersonPhone, Person.PhoneNumberType, Person.StateProvince |
| HumanResources.vEmployeeDepartment | VIEW | HumanResources.Department, HumanResources.Employee, HumanResources.EmployeeDepartmentHistory, Person.Person |
| HumanResources.vEmployeeDepartmentHistory | VIEW | HumanResources.Department, HumanResources.Employee, HumanResources.EmployeeDepartmentHistory, HumanResources.Shift, Person.Person |
| HumanResources.vJobCandidate | VIEW | HumanResources.JobCandidate, ref.value |
| HumanResources.vJobCandidateEducation | VIEW | HumanResources.JobCandidate, ref.value |
| HumanResources.vJobCandidateEmployment | VIEW | HumanResources.JobCandidate, ref.value |
| Person.vAdditionalContactInfo | VIEW | Person.Person, ref.value |
| Person.vStateProvinceCountryRegion | VIEW | Person.CountryRegion, Person.StateProvince |
| Production.vProductAndDescription | VIEW | Production.Product, Production.ProductDescription, Production.ProductModel, Production.ProductModelProductDescriptionCulture |
| Production.vProductModelCatalogDescription | VIEW | CatalogDescription.value, Production.ProductModel |
| Production.vProductModelInstructions | VIEW | Instructions.value, Production.ProductModel, ref.value |
| Purchasing.vVendorWithAddresses | VIEW | Person.Address, Person.AddressType, Person.BusinessEntityAddress, Person.CountryRegion, Person.StateProvince, Purchasing.Vendor |
| Purchasing.vVendorWithContacts | VIEW | Person.BusinessEntityContact, Person.ContactType, Person.EmailAddress, Person.Person, Person.PersonPhone, Person.PhoneNumberType, Purchasing.Vendor |
| Sales.vIndividualCustomer | VIEW | Person.Address, Person.AddressType, Person.BusinessEntityAddress, Person.CountryRegion, Person.EmailAddress, Person.Person, Person.PersonPhone, Person.PhoneNumberType, Person.StateProvince, Sales.Customer |
| Sales.vPersonDemographics | VIEW | Person.Person, ref.value |
| Sales.vSalesPerson | VIEW | HumanResources.Employee, Person.Address, Person.BusinessEntityAddress, Person.CountryRegion, Person.EmailAddress, Person.Person, Person.PersonPhone, Person.PhoneNumberType, Person.StateProvince, Sales.SalesPerson, Sales.SalesTerritory |
| Sales.vSalesPersonSalesByFiscalYears | VIEW | HumanResources.Employee, Person.Person, Sales.SalesOrderHeader, Sales.SalesPerson, Sales.SalesTerritory |
| Sales.vStoreWithAddresses | VIEW | Person.Address, Person.AddressType, Person.BusinessEntityAddress, Person.CountryRegion, Person.StateProvince, Sales.Store |
| Sales.vStoreWithContacts | VIEW | Person.BusinessEntityContact, Person.ContactType, Person.EmailAddress, Person.Person, Person.PersonPhone, Person.PhoneNumberType, Sales.Store |
| Sales.vStoreWithDemographics | VIEW | Demographics.value, Sales.Store |

### Stored procedures (10)

| Name | Type | References |
|---|---|---|
| dbo.uspGetBillOfMaterials | SQL_STORED_PROCEDURE | Production.BillOfMaterials, Production.Product |
| dbo.uspGetEmployeeManagers | SQL_STORED_PROCEDURE | HumanResources.Employee, OrganizationNode.GetAncestor, OrganizationNode.ToString, Person.Person |
| dbo.uspGetManagerEmployees | SQL_STORED_PROCEDURE | HumanResources.Employee, OrganizationNode.GetAncestor, OrganizationNode.ToString, Person.Person |
| dbo.uspGetWhereUsedProductID | SQL_STORED_PROCEDURE | Production.BillOfMaterials, Production.Product |
| dbo.uspLogError | SQL_STORED_PROCEDURE | dbo.ErrorLog, dbo.uspPrintError |
| dbo.uspPrintError | SQL_STORED_PROCEDURE |  |
| dbo.uspSearchCandidateResumes | SQL_STORED_PROCEDURE | HumanResources.JobCandidate |
| HumanResources.uspUpdateEmployeeHireInfo | SQL_STORED_PROCEDURE | HumanResources.Employee, HumanResources.EmployeePayHistory, dbo.Flag, dbo.uspLogError |
| HumanResources.uspUpdateEmployeeLogin | SQL_STORED_PROCEDURE | HumanResources.Employee, dbo.Flag, dbo.uspLogError |
| HumanResources.uspUpdateEmployeePersonalInfo | SQL_STORED_PROCEDURE | HumanResources.Employee, dbo.uspLogError |

### Functions (11)

| Name | Type | References |
|---|---|---|
| dbo.ufnGetAccountingEndDate | SQL_SCALAR_FUNCTION |  |
| dbo.ufnGetAccountingStartDate | SQL_SCALAR_FUNCTION |  |
| dbo.ufnGetDocumentStatusText | SQL_SCALAR_FUNCTION |  |
| dbo.ufnGetProductDealerPrice | SQL_SCALAR_FUNCTION | Production.Product, Production.ProductListPriceHistory |
| dbo.ufnGetProductListPrice | SQL_SCALAR_FUNCTION | Production.Product, Production.ProductListPriceHistory |
| dbo.ufnGetProductStandardCost | SQL_SCALAR_FUNCTION | Production.Product, Production.ProductCostHistory |
| dbo.ufnGetPurchaseOrderStatusText | SQL_SCALAR_FUNCTION |  |
| dbo.ufnGetSalesOrderStatusText | SQL_SCALAR_FUNCTION |  |
| dbo.ufnGetStock | SQL_SCALAR_FUNCTION | Production.ProductInventory |
| dbo.ufnLeadingZeros | SQL_SCALAR_FUNCTION |  |
| dbo.ufnGetContactInformation | SQL_TABLE_VALUED_FUNCTION | HumanResources.Employee, Person.BusinessEntityContact, Person.ContactType, Person.Person, Purchasing.Vendor, Sales.Customer, Sales.Store |

### Triggers (11)

| Trigger | On |
|---|---|
| iduSalesOrderDetail | Sales.SalesOrderDetail |
| uSalesOrderHeader | Sales.SalesOrderHeader |
| dVendor | Purchasing.Vendor |
| iWorkOrder | Production.WorkOrder |
| uWorkOrder | Production.WorkOrder |
| ddlDatabaseTriggerLog | DATABASE |
| dEmployee | HumanResources.Employee |
| iuPerson | Person.Person |
| iPurchaseOrderDetail | Purchasing.PurchaseOrderDetail |
| uPurchaseOrderDetail | Purchasing.PurchaseOrderDetail |
| uPurchaseOrderHeader | Purchasing.PurchaseOrderHeader |

### Table details

#### HumanResources.Department — 16 rows

PK: `DepartmentID`

| Column | Type | Null | Notes |
|---|---|---|---|
| DepartmentID | smallint |  | identity |
| Name | Name |  |  |
| GroupName | Name |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_Department_DepartmentID` clustered unique (DepartmentID); `AK_Department_Name` nonclustered unique (Name)

#### HumanResources.Employee — 290 rows

PK: `BusinessEntityID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| NationalIDNumber | nvarchar(15) |  |  |
| LoginID | nvarchar(256) |  |  |
| OrganizationNode | hierarchyid | Y |  |
| OrganizationLevel | smallint | Y | computed `([OrganizationNode].[GetLevel]())` |
| JobTitle | nvarchar(50) |  |  |
| BirthDate | date |  |  |
| MaritalStatus | nchar(1) |  |  |
| Gender | nchar(1) |  |  |
| HireDate | date |  |  |
| SalariedFlag | Flag |  | default `((1))` |
| VacationHours | smallint |  | default `((0))` |
| SickLeaveHours | smallint |  | default `((0))` |
| CurrentFlag | Flag |  | default `((1))` |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Person.Person(BusinessEntityID)

Indexes: `PK_Employee_BusinessEntityID` clustered unique (BusinessEntityID); `IX_Employee_OrganizationNode` nonclustered (OrganizationNode); `IX_Employee_OrganizationLevel_OrganizationNode` nonclustered (OrganizationLevel, OrganizationNode); `AK_Employee_LoginID` nonclustered unique (LoginID); `AK_Employee_NationalIDNumber` nonclustered unique (NationalIDNumber); `AK_Employee_rowguid` nonclustered unique (rowguid)

Triggers: dEmployee

#### HumanResources.EmployeeDepartmentHistory — 296 rows

PK: `BusinessEntityID, StartDate, DepartmentID, ShiftID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| DepartmentID | smallint |  |  |
| ShiftID | tinyint |  |  |
| StartDate | date |  |  |
| EndDate | date | Y |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (DepartmentID) → HumanResources.Department(DepartmentID); (BusinessEntityID) → HumanResources.Employee(BusinessEntityID); (ShiftID) → HumanResources.Shift(ShiftID)

Indexes: `PK_EmployeeDepartmentHistory_BusinessEntityID_StartDate_DepartmentID` clustered unique (BusinessEntityID, StartDate, DepartmentID, ShiftID); `IX_EmployeeDepartmentHistory_DepartmentID` nonclustered (DepartmentID); `IX_EmployeeDepartmentHistory_ShiftID` nonclustered (ShiftID)

#### HumanResources.EmployeePayHistory — 316 rows

PK: `BusinessEntityID, RateChangeDate`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| RateChangeDate | datetime |  |  |
| Rate | money |  |  |
| PayFrequency | tinyint |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → HumanResources.Employee(BusinessEntityID)

Indexes: `PK_EmployeePayHistory_BusinessEntityID_RateChangeDate` clustered unique (BusinessEntityID, RateChangeDate)

#### HumanResources.JobCandidate — 13 rows

PK: `JobCandidateID`

| Column | Type | Null | Notes |
|---|---|---|---|
| JobCandidateID | int |  | identity |
| BusinessEntityID | int | Y |  |
| Resume | xml | Y |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → HumanResources.Employee(BusinessEntityID)

Indexes: `PK_JobCandidate_JobCandidateID` clustered unique (JobCandidateID); `IX_JobCandidate_BusinessEntityID` nonclustered (BusinessEntityID)

#### HumanResources.Shift — 3 rows

PK: `ShiftID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ShiftID | tinyint |  | identity |
| Name | Name |  |  |
| StartTime | time |  |  |
| EndTime | time |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_Shift_ShiftID` clustered unique (ShiftID); `AK_Shift_Name` nonclustered unique (Name); `AK_Shift_StartTime_EndTime` nonclustered unique (StartTime, EndTime)

#### Person.Address — 19,614 rows

PK: `AddressID`

| Column | Type | Null | Notes |
|---|---|---|---|
| AddressID | int |  | identity |
| AddressLine1 | nvarchar(60) |  |  |
| AddressLine2 | nvarchar(60) | Y |  |
| City | nvarchar(30) |  |  |
| StateProvinceID | int |  |  |
| PostalCode | nvarchar(15) |  |  |
| SpatialLocation | geography | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (StateProvinceID) → Person.StateProvince(StateProvinceID)

Indexes: `PK_Address_AddressID` clustered unique (AddressID); `AK_Address_rowguid` nonclustered unique (rowguid); `IX_Address_AddressLine1_AddressLine2_City_StateProvinceID_PostalCode` nonclustered unique (AddressLine1, AddressLine2, City, StateProvinceID, PostalCode); `IX_Address_StateProvinceID` nonclustered (StateProvinceID)

#### Person.AddressType — 6 rows

PK: `AddressTypeID`

| Column | Type | Null | Notes |
|---|---|---|---|
| AddressTypeID | int |  | identity |
| Name | Name |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_AddressType_AddressTypeID` clustered unique (AddressTypeID); `AK_AddressType_rowguid` nonclustered unique (rowguid); `AK_AddressType_Name` nonclustered unique (Name)

#### Person.BusinessEntity — 20,777 rows

PK: `BusinessEntityID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  | identity |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_BusinessEntity_BusinessEntityID` clustered unique (BusinessEntityID); `AK_BusinessEntity_rowguid` nonclustered unique (rowguid)

#### Person.BusinessEntityAddress — 19,614 rows

PK: `BusinessEntityID, AddressID, AddressTypeID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| AddressID | int |  |  |
| AddressTypeID | int |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (AddressID) → Person.Address(AddressID); (AddressTypeID) → Person.AddressType(AddressTypeID); (BusinessEntityID) → Person.BusinessEntity(BusinessEntityID)

Indexes: `PK_BusinessEntityAddress_BusinessEntityID_AddressID_AddressTypeID` clustered unique (BusinessEntityID, AddressID, AddressTypeID); `AK_BusinessEntityAddress_rowguid` nonclustered unique (rowguid); `IX_BusinessEntityAddress_AddressID` nonclustered (AddressID); `IX_BusinessEntityAddress_AddressTypeID` nonclustered (AddressTypeID)

#### Person.BusinessEntityContact — 909 rows

PK: `BusinessEntityID, PersonID, ContactTypeID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| PersonID | int |  |  |
| ContactTypeID | int |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (PersonID) → Person.Person(BusinessEntityID); (ContactTypeID) → Person.ContactType(ContactTypeID); (BusinessEntityID) → Person.BusinessEntity(BusinessEntityID)

Indexes: `PK_BusinessEntityContact_BusinessEntityID_PersonID_ContactTypeID` clustered unique (BusinessEntityID, PersonID, ContactTypeID); `AK_BusinessEntityContact_rowguid` nonclustered unique (rowguid); `IX_BusinessEntityContact_PersonID` nonclustered (PersonID); `IX_BusinessEntityContact_ContactTypeID` nonclustered (ContactTypeID)

#### Person.ContactType — 20 rows

PK: `ContactTypeID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ContactTypeID | int |  | identity |
| Name | Name |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_ContactType_ContactTypeID` clustered unique (ContactTypeID); `AK_ContactType_Name` nonclustered unique (Name)

#### Person.CountryRegion — 238 rows

PK: `CountryRegionCode`

| Column | Type | Null | Notes |
|---|---|---|---|
| CountryRegionCode | nvarchar(3) |  |  |
| Name | Name |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_CountryRegion_CountryRegionCode` clustered unique (CountryRegionCode); `AK_CountryRegion_Name` nonclustered unique (Name)

#### Person.EmailAddress — 19,972 rows

PK: `BusinessEntityID, EmailAddressID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| EmailAddressID | int |  | identity |
| EmailAddress | nvarchar(50) | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Person.Person(BusinessEntityID)

Indexes: `PK_EmailAddress_BusinessEntityID_EmailAddressID` clustered unique (BusinessEntityID, EmailAddressID); `IX_EmailAddress_EmailAddress` nonclustered (EmailAddress)

#### Person.Password — 19,972 rows

PK: `BusinessEntityID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| PasswordHash | varchar(128) |  |  |
| PasswordSalt | varchar(10) |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Person.Person(BusinessEntityID)

Indexes: `PK_Password_BusinessEntityID` clustered unique (BusinessEntityID)

#### Person.Person — 19,972 rows

PK: `BusinessEntityID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| PersonType | nchar(2) |  |  |
| NameStyle | NameStyle |  | default `((0))` |
| Title | nvarchar(8) | Y |  |
| FirstName | Name |  |  |
| MiddleName | Name | Y |  |
| LastName | Name |  |  |
| Suffix | nvarchar(10) | Y |  |
| EmailPromotion | int |  | default `((0))` |
| AdditionalContactInfo | xml | Y |  |
| Demographics | xml | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Person.BusinessEntity(BusinessEntityID)

Indexes: `PK_Person_BusinessEntityID` clustered unique (BusinessEntityID); `IX_Person_LastName_FirstName_MiddleName` nonclustered (LastName, FirstName, MiddleName); `AK_Person_rowguid` nonclustered unique (rowguid); `PXML_Person_AddContact` xml (AdditionalContactInfo); `PXML_Person_Demographics` xml (Demographics); `XMLPATH_Person_Demographics` xml (Demographics); `XMLPROPERTY_Person_Demographics` xml (Demographics); `XMLVALUE_Person_Demographics` xml (Demographics)

Triggers: iuPerson

#### Person.PersonPhone — 19,972 rows

PK: `BusinessEntityID, PhoneNumber, PhoneNumberTypeID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| PhoneNumber | Phone |  |  |
| PhoneNumberTypeID | int |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Person.Person(BusinessEntityID); (PhoneNumberTypeID) → Person.PhoneNumberType(PhoneNumberTypeID)

Indexes: `PK_PersonPhone_BusinessEntityID_PhoneNumber_PhoneNumberTypeID` clustered unique (BusinessEntityID, PhoneNumber, PhoneNumberTypeID); `IX_PersonPhone_PhoneNumber` nonclustered (PhoneNumber)

#### Person.PhoneNumberType — 3 rows

PK: `PhoneNumberTypeID`

| Column | Type | Null | Notes |
|---|---|---|---|
| PhoneNumberTypeID | int |  | identity |
| Name | Name |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_PhoneNumberType_PhoneNumberTypeID` clustered unique (PhoneNumberTypeID)

#### Person.StateProvince — 181 rows

PK: `StateProvinceID`

| Column | Type | Null | Notes |
|---|---|---|---|
| StateProvinceID | int |  | identity |
| StateProvinceCode | nchar(3) |  |  |
| CountryRegionCode | nvarchar(3) |  |  |
| IsOnlyStateProvinceFlag | Flag |  | default `((1))` |
| Name | Name |  |  |
| TerritoryID | int |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (CountryRegionCode) → Person.CountryRegion(CountryRegionCode); (TerritoryID) → Sales.SalesTerritory(TerritoryID)

Indexes: `PK_StateProvince_StateProvinceID` clustered unique (StateProvinceID); `AK_StateProvince_Name` nonclustered unique (Name); `AK_StateProvince_StateProvinceCode_CountryRegionCode` nonclustered unique (StateProvinceCode, CountryRegionCode); `AK_StateProvince_rowguid` nonclustered unique (rowguid)

#### Production.BillOfMaterials — 2,679 rows

PK: `BillOfMaterialsID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BillOfMaterialsID | int |  | identity |
| ProductAssemblyID | int | Y |  |
| ComponentID | int |  |  |
| StartDate | datetime |  | default `(getdate())` |
| EndDate | datetime | Y |  |
| UnitMeasureCode | nchar(3) |  |  |
| BOMLevel | smallint |  |  |
| PerAssemblyQty | decimal(8,2) |  | default `((1.00))` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductAssemblyID) → Production.Product(ProductID); (ComponentID) → Production.Product(ProductID); (UnitMeasureCode) → Production.UnitMeasure(UnitMeasureCode)

Indexes: `AK_BillOfMaterials_ProductAssemblyID_ComponentID_StartDate` clustered unique (ProductAssemblyID, ComponentID, StartDate); `PK_BillOfMaterials_BillOfMaterialsID` nonclustered unique (BillOfMaterialsID); `IX_BillOfMaterials_UnitMeasureCode` nonclustered (UnitMeasureCode)

#### Production.Culture — 8 rows

PK: `CultureID`

| Column | Type | Null | Notes |
|---|---|---|---|
| CultureID | nchar(6) |  |  |
| Name | Name |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_Culture_CultureID` clustered unique (CultureID); `AK_Culture_Name` nonclustered unique (Name)

#### Production.Document — 13 rows

PK: `DocumentNode`

| Column | Type | Null | Notes |
|---|---|---|---|
| DocumentNode | hierarchyid |  |  |
| DocumentLevel | smallint | Y | computed `([DocumentNode].[GetLevel]())` |
| Title | nvarchar(50) |  |  |
| Owner | int |  |  |
| FolderFlag | bit |  | default `((0))` |
| FileName | nvarchar(400) |  |  |
| FileExtension | nvarchar(8) |  |  |
| Revision | nchar(5) |  |  |
| ChangeNumber | int |  | default `((0))` |
| Status | tinyint |  |  |
| DocumentSummary | nvarchar(max) | Y |  |
| Document | varbinary(max) | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (Owner) → HumanResources.Employee(BusinessEntityID)

Indexes: `PK_Document_DocumentNode` clustered unique (DocumentNode); `UQ__Document__F73921F7C81C642F` nonclustered unique (rowguid); `AK_Document_DocumentLevel_DocumentNode` nonclustered unique (DocumentLevel, DocumentNode); `AK_Document_rowguid` nonclustered unique (rowguid); `IX_Document_FileName_Revision` nonclustered (FileName, Revision)

#### Production.Illustration — 5 rows

PK: `IllustrationID`

| Column | Type | Null | Notes |
|---|---|---|---|
| IllustrationID | int |  | identity |
| Diagram | xml | Y |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_Illustration_IllustrationID` clustered unique (IllustrationID)

#### Production.Location — 14 rows

PK: `LocationID`

| Column | Type | Null | Notes |
|---|---|---|---|
| LocationID | smallint |  | identity |
| Name | Name |  |  |
| CostRate | smallmoney |  | default `((0.00))` |
| Availability | decimal(8,2) |  | default `((0.00))` |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_Location_LocationID` clustered unique (LocationID); `AK_Location_Name` nonclustered unique (Name)

#### Production.Product — 504 rows

PK: `ProductID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductID | int |  | identity |
| Name | Name |  |  |
| ProductNumber | nvarchar(25) |  |  |
| MakeFlag | Flag |  | default `((1))` |
| FinishedGoodsFlag | Flag |  | default `((1))` |
| Color | nvarchar(15) | Y |  |
| SafetyStockLevel | smallint |  |  |
| ReorderPoint | smallint |  |  |
| StandardCost | money |  |  |
| ListPrice | money |  |  |
| Size | nvarchar(5) | Y |  |
| SizeUnitMeasureCode | nchar(3) | Y |  |
| WeightUnitMeasureCode | nchar(3) | Y |  |
| Weight | decimal(8,2) | Y |  |
| DaysToManufacture | int |  |  |
| ProductLine | nchar(2) | Y |  |
| Class | nchar(2) | Y |  |
| Style | nchar(2) | Y |  |
| ProductSubcategoryID | int | Y |  |
| ProductModelID | int | Y |  |
| SellStartDate | datetime |  |  |
| SellEndDate | datetime | Y |  |
| DiscontinuedDate | datetime | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (SizeUnitMeasureCode) → Production.UnitMeasure(UnitMeasureCode); (WeightUnitMeasureCode) → Production.UnitMeasure(UnitMeasureCode); (ProductModelID) → Production.ProductModel(ProductModelID); (ProductSubcategoryID) → Production.ProductSubcategory(ProductSubcategoryID)

Indexes: `PK_Product_ProductID` clustered unique (ProductID); `AK_Product_ProductNumber` nonclustered unique (ProductNumber); `AK_Product_Name` nonclustered unique (Name); `AK_Product_rowguid` nonclustered unique (rowguid)

#### Production.ProductCategory — 4 rows

PK: `ProductCategoryID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductCategoryID | int |  | identity |
| Name | Name |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_ProductCategory_ProductCategoryID` clustered unique (ProductCategoryID); `AK_ProductCategory_Name` nonclustered unique (Name); `AK_ProductCategory_rowguid` nonclustered unique (rowguid)

#### Production.ProductCostHistory — 395 rows

PK: `ProductID, StartDate`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductID | int |  |  |
| StartDate | datetime |  |  |
| EndDate | datetime | Y |  |
| StandardCost | money |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID)

Indexes: `PK_ProductCostHistory_ProductID_StartDate` clustered unique (ProductID, StartDate)

#### Production.ProductDescription — 762 rows

PK: `ProductDescriptionID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductDescriptionID | int |  | identity |
| Description | nvarchar(400) |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_ProductDescription_ProductDescriptionID` clustered unique (ProductDescriptionID); `AK_ProductDescription_rowguid` nonclustered unique (rowguid)

#### Production.ProductDocument — 32 rows

PK: `ProductID, DocumentNode`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductID | int |  |  |
| DocumentNode | hierarchyid |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID); (DocumentNode) → Production.Document(DocumentNode)

Indexes: `PK_ProductDocument_ProductID_DocumentNode` clustered unique (ProductID, DocumentNode)

#### Production.ProductInventory — 1,069 rows

PK: `ProductID, LocationID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductID | int |  |  |
| LocationID | smallint |  |  |
| Shelf | nvarchar(10) |  |  |
| Bin | tinyint |  |  |
| Quantity | smallint |  | default `((0))` |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (LocationID) → Production.Location(LocationID); (ProductID) → Production.Product(ProductID)

Indexes: `PK_ProductInventory_ProductID_LocationID` clustered unique (ProductID, LocationID)

#### Production.ProductListPriceHistory — 395 rows

PK: `ProductID, StartDate`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductID | int |  |  |
| StartDate | datetime |  |  |
| EndDate | datetime | Y |  |
| ListPrice | money |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID)

Indexes: `PK_ProductListPriceHistory_ProductID_StartDate` clustered unique (ProductID, StartDate)

#### Production.ProductModel — 128 rows

PK: `ProductModelID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductModelID | int |  | identity |
| Name | Name |  |  |
| CatalogDescription | xml | Y |  |
| Instructions | xml | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_ProductModel_ProductModelID` clustered unique (ProductModelID); `AK_ProductModel_Name` nonclustered unique (Name); `AK_ProductModel_rowguid` nonclustered unique (rowguid); `PXML_ProductModel_CatalogDescription` xml (CatalogDescription); `PXML_ProductModel_Instructions` xml (Instructions)

#### Production.ProductModelIllustration — 7 rows

PK: `ProductModelID, IllustrationID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductModelID | int |  |  |
| IllustrationID | int |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductModelID) → Production.ProductModel(ProductModelID); (IllustrationID) → Production.Illustration(IllustrationID)

Indexes: `PK_ProductModelIllustration_ProductModelID_IllustrationID` clustered unique (ProductModelID, IllustrationID)

#### Production.ProductModelProductDescriptionCulture — 762 rows

PK: `ProductModelID, ProductDescriptionID, CultureID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductModelID | int |  |  |
| ProductDescriptionID | int |  |  |
| CultureID | nchar(6) |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductDescriptionID) → Production.ProductDescription(ProductDescriptionID); (CultureID) → Production.Culture(CultureID); (ProductModelID) → Production.ProductModel(ProductModelID)

Indexes: `PK_ProductModelProductDescriptionCulture_ProductModelID_ProductDescriptionID_CultureID` clustered unique (ProductModelID, ProductDescriptionID, CultureID)

#### Production.ProductPhoto — 101 rows

PK: `ProductPhotoID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductPhotoID | int |  | identity |
| ThumbNailPhoto | varbinary(max) | Y |  |
| ThumbnailPhotoFileName | nvarchar(50) | Y |  |
| LargePhoto | varbinary(max) | Y |  |
| LargePhotoFileName | nvarchar(50) | Y |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_ProductPhoto_ProductPhotoID` clustered unique (ProductPhotoID)

#### Production.ProductProductPhoto — 504 rows

PK: `ProductID, ProductPhotoID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductID | int |  |  |
| ProductPhotoID | int |  |  |
| Primary | Flag |  | default `((0))` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID); (ProductPhotoID) → Production.ProductPhoto(ProductPhotoID)

Indexes: `PK_ProductProductPhoto_ProductID_ProductPhotoID` nonclustered unique (ProductID, ProductPhotoID)

#### Production.ProductReview — 4 rows

PK: `ProductReviewID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductReviewID | int |  | identity |
| ProductID | int |  |  |
| ReviewerName | Name |  |  |
| ReviewDate | datetime |  | default `(getdate())` |
| EmailAddress | nvarchar(50) |  |  |
| Rating | int |  |  |
| Comments | nvarchar(3850) | Y |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID)

Indexes: `PK_ProductReview_ProductReviewID` clustered unique (ProductReviewID); `IX_ProductReview_ProductID_Name` nonclustered (ProductID, ReviewerName) incl. Comments

#### Production.ProductSubcategory — 37 rows

PK: `ProductSubcategoryID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductSubcategoryID | int |  | identity |
| ProductCategoryID | int |  |  |
| Name | Name |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductCategoryID) → Production.ProductCategory(ProductCategoryID)

Indexes: `PK_ProductSubcategory_ProductSubcategoryID` clustered unique (ProductSubcategoryID); `AK_ProductSubcategory_Name` nonclustered unique (Name); `AK_ProductSubcategory_rowguid` nonclustered unique (rowguid)

#### Production.ScrapReason — 16 rows

PK: `ScrapReasonID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ScrapReasonID | smallint |  | identity |
| Name | Name |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_ScrapReason_ScrapReasonID` clustered unique (ScrapReasonID); `AK_ScrapReason_Name` nonclustered unique (Name)

#### Production.TransactionHistory — 113,443 rows

PK: `TransactionID`

| Column | Type | Null | Notes |
|---|---|---|---|
| TransactionID | int |  | identity |
| ProductID | int |  |  |
| ReferenceOrderID | int |  |  |
| ReferenceOrderLineID | int |  | default `((0))` |
| TransactionDate | datetime |  | default `(getdate())` |
| TransactionType | nchar(1) |  |  |
| Quantity | int |  |  |
| ActualCost | money |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID)

Indexes: `PK_TransactionHistory_TransactionID` clustered unique (TransactionID); `IX_TransactionHistory_ProductID` nonclustered (ProductID); `IX_TransactionHistory_ReferenceOrderID_ReferenceOrderLineID` nonclustered (ReferenceOrderID, ReferenceOrderLineID)

#### Production.TransactionHistoryArchive — 89,253 rows

PK: `TransactionID`

| Column | Type | Null | Notes |
|---|---|---|---|
| TransactionID | int |  |  |
| ProductID | int |  |  |
| ReferenceOrderID | int |  |  |
| ReferenceOrderLineID | int |  | default `((0))` |
| TransactionDate | datetime |  | default `(getdate())` |
| TransactionType | nchar(1) |  |  |
| Quantity | int |  |  |
| ActualCost | money |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_TransactionHistoryArchive_TransactionID` clustered unique (TransactionID); `IX_TransactionHistoryArchive_ProductID` nonclustered (ProductID); `IX_TransactionHistoryArchive_ReferenceOrderID_ReferenceOrderLineID` nonclustered (ReferenceOrderID, ReferenceOrderLineID)

#### Production.UnitMeasure — 38 rows

PK: `UnitMeasureCode`

| Column | Type | Null | Notes |
|---|---|---|---|
| UnitMeasureCode | nchar(3) |  |  |
| Name | Name |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_UnitMeasure_UnitMeasureCode` clustered unique (UnitMeasureCode); `AK_UnitMeasure_Name` nonclustered unique (Name)

#### Production.WorkOrder — 72,591 rows

PK: `WorkOrderID`

| Column | Type | Null | Notes |
|---|---|---|---|
| WorkOrderID | int |  | identity |
| ProductID | int |  |  |
| OrderQty | int |  |  |
| StockedQty | int |  | computed `(isnull([OrderQty]-[ScrappedQty],(0)))` |
| ScrappedQty | smallint |  |  |
| StartDate | datetime |  |  |
| EndDate | datetime | Y |  |
| DueDate | datetime |  |  |
| ScrapReasonID | smallint | Y |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID); (ScrapReasonID) → Production.ScrapReason(ScrapReasonID)

Indexes: `PK_WorkOrder_WorkOrderID` clustered unique (WorkOrderID); `IX_WorkOrder_ScrapReasonID` nonclustered (ScrapReasonID); `IX_WorkOrder_ProductID` nonclustered (ProductID)

Triggers: iWorkOrder, uWorkOrder

#### Production.WorkOrderRouting — 67,131 rows

PK: `WorkOrderID, ProductID, OperationSequence`

| Column | Type | Null | Notes |
|---|---|---|---|
| WorkOrderID | int |  |  |
| ProductID | int |  |  |
| OperationSequence | smallint |  |  |
| LocationID | smallint |  |  |
| ScheduledStartDate | datetime |  |  |
| ScheduledEndDate | datetime |  |  |
| ActualStartDate | datetime | Y |  |
| ActualEndDate | datetime | Y |  |
| ActualResourceHrs | decimal(9,4) | Y |  |
| PlannedCost | money |  |  |
| ActualCost | money | Y |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (LocationID) → Production.Location(LocationID); (WorkOrderID) → Production.WorkOrder(WorkOrderID)

Indexes: `PK_WorkOrderRouting_WorkOrderID_ProductID_OperationSequence` clustered unique (WorkOrderID, ProductID, OperationSequence); `IX_WorkOrderRouting_ProductID` nonclustered (ProductID)

#### Purchasing.ProductVendor — 460 rows

PK: `ProductID, BusinessEntityID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductID | int |  |  |
| BusinessEntityID | int |  |  |
| AverageLeadTime | int |  |  |
| StandardPrice | money |  |  |
| LastReceiptCost | money | Y |  |
| LastReceiptDate | datetime | Y |  |
| MinOrderQty | int |  |  |
| MaxOrderQty | int |  |  |
| OnOrderQty | int | Y |  |
| UnitMeasureCode | nchar(3) |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID); (UnitMeasureCode) → Production.UnitMeasure(UnitMeasureCode); (BusinessEntityID) → Purchasing.Vendor(BusinessEntityID)

Indexes: `PK_ProductVendor_ProductID_BusinessEntityID` clustered unique (ProductID, BusinessEntityID); `IX_ProductVendor_UnitMeasureCode` nonclustered (UnitMeasureCode); `IX_ProductVendor_BusinessEntityID` nonclustered (BusinessEntityID)

#### Purchasing.PurchaseOrderDetail — 8,845 rows

PK: `PurchaseOrderID, PurchaseOrderDetailID`

| Column | Type | Null | Notes |
|---|---|---|---|
| PurchaseOrderID | int |  |  |
| PurchaseOrderDetailID | int |  | identity |
| DueDate | datetime |  |  |
| OrderQty | smallint |  |  |
| ProductID | int |  |  |
| UnitPrice | money |  |  |
| LineTotal | money |  | computed `(isnull([OrderQty]*[UnitPrice],(0.00)))` |
| ReceivedQty | decimal(8,2) |  |  |
| RejectedQty | decimal(8,2) |  |  |
| StockedQty | decimal(9,2) |  | computed `(isnull([ReceivedQty]-[RejectedQty],(0.00)))` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID); (PurchaseOrderID) → Purchasing.PurchaseOrderHeader(PurchaseOrderID)

Indexes: `PK_PurchaseOrderDetail_PurchaseOrderID_PurchaseOrderDetailID` clustered unique (PurchaseOrderID, PurchaseOrderDetailID); `IX_PurchaseOrderDetail_ProductID` nonclustered (ProductID)

Triggers: iPurchaseOrderDetail, uPurchaseOrderDetail

#### Purchasing.PurchaseOrderHeader — 4,012 rows

PK: `PurchaseOrderID`

| Column | Type | Null | Notes |
|---|---|---|---|
| PurchaseOrderID | int |  | identity |
| RevisionNumber | tinyint |  | default `((0))` |
| Status | tinyint |  | default `((1))` |
| EmployeeID | int |  |  |
| VendorID | int |  |  |
| ShipMethodID | int |  |  |
| OrderDate | datetime |  | default `(getdate())` |
| ShipDate | datetime | Y |  |
| SubTotal | money |  | default `((0.00))` |
| TaxAmt | money |  | default `((0.00))` |
| Freight | money |  | default `((0.00))` |
| TotalDue | money |  | computed `(isnull(([SubTotal]+[TaxAmt])+[Freight],(0)))` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (EmployeeID) → HumanResources.Employee(BusinessEntityID); (VendorID) → Purchasing.Vendor(BusinessEntityID); (ShipMethodID) → Purchasing.ShipMethod(ShipMethodID)

Indexes: `PK_PurchaseOrderHeader_PurchaseOrderID` clustered unique (PurchaseOrderID); `IX_PurchaseOrderHeader_VendorID` nonclustered (VendorID); `IX_PurchaseOrderHeader_EmployeeID` nonclustered (EmployeeID)

Triggers: uPurchaseOrderHeader

#### Purchasing.ShipMethod — 5 rows

PK: `ShipMethodID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ShipMethodID | int |  | identity |
| Name | Name |  |  |
| ShipBase | money |  | default `((0.00))` |
| ShipRate | money |  | default `((0.00))` |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_ShipMethod_ShipMethodID` clustered unique (ShipMethodID); `AK_ShipMethod_Name` nonclustered unique (Name); `AK_ShipMethod_rowguid` nonclustered unique (rowguid)

#### Purchasing.Vendor — 104 rows

PK: `BusinessEntityID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| AccountNumber | AccountNumber |  |  |
| Name | Name |  |  |
| CreditRating | tinyint |  |  |
| PreferredVendorStatus | Flag |  | default `((1))` |
| ActiveFlag | Flag |  | default `((1))` |
| PurchasingWebServiceURL | nvarchar(1024) | Y |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Person.BusinessEntity(BusinessEntityID)

Indexes: `PK_Vendor_BusinessEntityID` clustered unique (BusinessEntityID); `AK_Vendor_AccountNumber` nonclustered unique (AccountNumber)

Triggers: dVendor

#### Sales.CountryRegionCurrency — 109 rows

PK: `CountryRegionCode, CurrencyCode`

| Column | Type | Null | Notes |
|---|---|---|---|
| CountryRegionCode | nvarchar(3) |  |  |
| CurrencyCode | nchar(3) |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (CountryRegionCode) → Person.CountryRegion(CountryRegionCode); (CurrencyCode) → Sales.Currency(CurrencyCode)

Indexes: `PK_CountryRegionCurrency_CountryRegionCode_CurrencyCode` clustered unique (CountryRegionCode, CurrencyCode); `IX_CountryRegionCurrency_CurrencyCode` nonclustered (CurrencyCode)

#### Sales.CreditCard — 19,118 rows

PK: `CreditCardID`

| Column | Type | Null | Notes |
|---|---|---|---|
| CreditCardID | int |  | identity |
| CardType | nvarchar(50) |  |  |
| CardNumber | nvarchar(25) |  |  |
| ExpMonth | tinyint |  |  |
| ExpYear | smallint |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_CreditCard_CreditCardID` clustered unique (CreditCardID); `AK_CreditCard_CardNumber` nonclustered unique (CardNumber)

#### Sales.Currency — 105 rows

PK: `CurrencyCode`

| Column | Type | Null | Notes |
|---|---|---|---|
| CurrencyCode | nchar(3) |  |  |
| Name | Name |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_Currency_CurrencyCode` clustered unique (CurrencyCode); `AK_Currency_Name` nonclustered unique (Name)

#### Sales.CurrencyRate — 13,532 rows

PK: `CurrencyRateID`

| Column | Type | Null | Notes |
|---|---|---|---|
| CurrencyRateID | int |  | identity |
| CurrencyRateDate | datetime |  |  |
| FromCurrencyCode | nchar(3) |  |  |
| ToCurrencyCode | nchar(3) |  |  |
| AverageRate | money |  |  |
| EndOfDayRate | money |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (FromCurrencyCode) → Sales.Currency(CurrencyCode); (ToCurrencyCode) → Sales.Currency(CurrencyCode)

Indexes: `PK_CurrencyRate_CurrencyRateID` clustered unique (CurrencyRateID); `AK_CurrencyRate_CurrencyRateDate_FromCurrencyCode_ToCurrencyCode` nonclustered unique (CurrencyRateDate, FromCurrencyCode, ToCurrencyCode)

#### Sales.Customer — 19,820 rows

PK: `CustomerID`

| Column | Type | Null | Notes |
|---|---|---|---|
| CustomerID | int |  | identity |
| PersonID | int | Y |  |
| StoreID | int | Y |  |
| TerritoryID | int | Y |  |
| AccountNumber | varchar(10) |  | computed `(isnull('AW'+[dbo].[ufnLeadingZeros]([CustomerID]),''))` |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (PersonID) → Person.Person(BusinessEntityID); (StoreID) → Sales.Store(BusinessEntityID); (TerritoryID) → Sales.SalesTerritory(TerritoryID)

Indexes: `PK_Customer_CustomerID` clustered unique (CustomerID); `AK_Customer_rowguid` nonclustered unique (rowguid); `AK_Customer_AccountNumber` nonclustered unique (AccountNumber); `IX_Customer_TerritoryID` nonclustered (TerritoryID)

#### Sales.PersonCreditCard — 19,118 rows

PK: `BusinessEntityID, CreditCardID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| CreditCardID | int |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Person.Person(BusinessEntityID); (CreditCardID) → Sales.CreditCard(CreditCardID)

Indexes: `PK_PersonCreditCard_BusinessEntityID_CreditCardID` clustered unique (BusinessEntityID, CreditCardID)

#### Sales.SalesOrderDetail — 121,317 rows

PK: `SalesOrderID, SalesOrderDetailID`

| Column | Type | Null | Notes |
|---|---|---|---|
| SalesOrderID | int |  |  |
| SalesOrderDetailID | int |  | identity |
| CarrierTrackingNumber | nvarchar(25) | Y |  |
| OrderQty | smallint |  |  |
| ProductID | int |  |  |
| SpecialOfferID | int |  |  |
| UnitPrice | money |  |  |
| UnitPriceDiscount | money |  | default `((0.0))` |
| LineTotal | numeric(38,6) |  | computed `(isnull(([UnitPrice]*((1.0)-[UnitPriceDiscount]))*[OrderQty],(0.0)))` |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (SalesOrderID) → Sales.SalesOrderHeader(SalesOrderID); (SpecialOfferID, ProductID) → Sales.SpecialOfferProduct(SpecialOfferID, ProductID)

Indexes: `PK_SalesOrderDetail_SalesOrderID_SalesOrderDetailID` clustered unique (SalesOrderID, SalesOrderDetailID); `AK_SalesOrderDetail_rowguid` nonclustered unique (rowguid); `IX_SalesOrderDetail_ProductID` nonclustered (ProductID)

Triggers: iduSalesOrderDetail

#### Sales.SalesOrderHeader — 31,465 rows

PK: `SalesOrderID`

| Column | Type | Null | Notes |
|---|---|---|---|
| SalesOrderID | int |  | identity |
| RevisionNumber | tinyint |  | default `((0))` |
| OrderDate | datetime |  | default `(getdate())` |
| DueDate | datetime |  |  |
| ShipDate | datetime | Y |  |
| Status | tinyint |  | default `((1))` |
| OnlineOrderFlag | Flag |  | default `((1))` |
| SalesOrderNumber | nvarchar(25) |  | computed `(isnull(N'SO'+CONVERT([nvarchar](23),[SalesOrderID]),N'*** ERROR ***'))` |
| PurchaseOrderNumber | OrderNumber | Y |  |
| AccountNumber | AccountNumber | Y |  |
| CustomerID | int |  |  |
| SalesPersonID | int | Y |  |
| TerritoryID | int | Y |  |
| BillToAddressID | int |  |  |
| ShipToAddressID | int |  |  |
| ShipMethodID | int |  |  |
| CreditCardID | int | Y |  |
| CreditCardApprovalCode | varchar(15) | Y |  |
| CurrencyRateID | int | Y |  |
| SubTotal | money |  | default `((0.00))` |
| TaxAmt | money |  | default `((0.00))` |
| Freight | money |  | default `((0.00))` |
| TotalDue | money |  | computed `(isnull(([SubTotal]+[TaxAmt])+[Freight],(0)))` |
| Comment | nvarchar(128) | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BillToAddressID) → Person.Address(AddressID); (ShipToAddressID) → Person.Address(AddressID); (CreditCardID) → Sales.CreditCard(CreditCardID); (CurrencyRateID) → Sales.CurrencyRate(CurrencyRateID); (CustomerID) → Sales.Customer(CustomerID); (SalesPersonID) → Sales.SalesPerson(BusinessEntityID); (ShipMethodID) → Purchasing.ShipMethod(ShipMethodID); (TerritoryID) → Sales.SalesTerritory(TerritoryID)

Indexes: `PK_SalesOrderHeader_SalesOrderID` clustered unique (SalesOrderID); `AK_SalesOrderHeader_rowguid` nonclustered unique (rowguid); `AK_SalesOrderHeader_SalesOrderNumber` nonclustered unique (SalesOrderNumber); `IX_SalesOrderHeader_CustomerID` nonclustered (CustomerID); `IX_SalesOrderHeader_SalesPersonID` nonclustered (SalesPersonID)

Triggers: uSalesOrderHeader

#### Sales.SalesOrderHeaderSalesReason — 27,647 rows

PK: `SalesOrderID, SalesReasonID`

| Column | Type | Null | Notes |
|---|---|---|---|
| SalesOrderID | int |  |  |
| SalesReasonID | int |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (SalesReasonID) → Sales.SalesReason(SalesReasonID); (SalesOrderID) → Sales.SalesOrderHeader(SalesOrderID)

Indexes: `PK_SalesOrderHeaderSalesReason_SalesOrderID_SalesReasonID` clustered unique (SalesOrderID, SalesReasonID)

#### Sales.SalesPerson — 17 rows

PK: `BusinessEntityID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| TerritoryID | int | Y |  |
| SalesQuota | money | Y |  |
| Bonus | money |  | default `((0.00))` |
| CommissionPct | smallmoney |  | default `((0.00))` |
| SalesYTD | money |  | default `((0.00))` |
| SalesLastYear | money |  | default `((0.00))` |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → HumanResources.Employee(BusinessEntityID); (TerritoryID) → Sales.SalesTerritory(TerritoryID)

Indexes: `PK_SalesPerson_BusinessEntityID` clustered unique (BusinessEntityID); `AK_SalesPerson_rowguid` nonclustered unique (rowguid)

#### Sales.SalesPersonQuotaHistory — 163 rows

PK: `BusinessEntityID, QuotaDate`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| QuotaDate | datetime |  |  |
| SalesQuota | money |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Sales.SalesPerson(BusinessEntityID)

Indexes: `PK_SalesPersonQuotaHistory_BusinessEntityID_QuotaDate` clustered unique (BusinessEntityID, QuotaDate); `AK_SalesPersonQuotaHistory_rowguid` nonclustered unique (rowguid)

#### Sales.SalesReason — 10 rows

PK: `SalesReasonID`

| Column | Type | Null | Notes |
|---|---|---|---|
| SalesReasonID | int |  | identity |
| Name | Name |  |  |
| ReasonType | Name |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_SalesReason_SalesReasonID` clustered unique (SalesReasonID)

#### Sales.SalesTaxRate — 29 rows

PK: `SalesTaxRateID`

| Column | Type | Null | Notes |
|---|---|---|---|
| SalesTaxRateID | int |  | identity |
| StateProvinceID | int |  |  |
| TaxType | tinyint |  |  |
| TaxRate | smallmoney |  | default `((0.00))` |
| Name | Name |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (StateProvinceID) → Person.StateProvince(StateProvinceID)

Indexes: `PK_SalesTaxRate_SalesTaxRateID` clustered unique (SalesTaxRateID); `AK_SalesTaxRate_StateProvinceID_TaxType` nonclustered unique (StateProvinceID, TaxType); `AK_SalesTaxRate_rowguid` nonclustered unique (rowguid)

#### Sales.SalesTerritory — 10 rows

PK: `TerritoryID`

| Column | Type | Null | Notes |
|---|---|---|---|
| TerritoryID | int |  | identity |
| Name | Name |  |  |
| CountryRegionCode | nvarchar(3) |  |  |
| Group | nvarchar(50) |  |  |
| SalesYTD | money |  | default `((0.00))` |
| SalesLastYear | money |  | default `((0.00))` |
| CostYTD | money |  | default `((0.00))` |
| CostLastYear | money |  | default `((0.00))` |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (CountryRegionCode) → Person.CountryRegion(CountryRegionCode)

Indexes: `PK_SalesTerritory_TerritoryID` clustered unique (TerritoryID); `AK_SalesTerritory_Name` nonclustered unique (Name); `AK_SalesTerritory_rowguid` nonclustered unique (rowguid)

#### Sales.SalesTerritoryHistory — 17 rows

PK: `BusinessEntityID, StartDate, TerritoryID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| TerritoryID | int |  |  |
| StartDate | datetime |  |  |
| EndDate | datetime | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Sales.SalesPerson(BusinessEntityID); (TerritoryID) → Sales.SalesTerritory(TerritoryID)

Indexes: `PK_SalesTerritoryHistory_BusinessEntityID_StartDate_TerritoryID` clustered unique (BusinessEntityID, StartDate, TerritoryID); `AK_SalesTerritoryHistory_rowguid` nonclustered unique (rowguid)

#### Sales.ShoppingCartItem — 3 rows

PK: `ShoppingCartItemID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ShoppingCartItemID | int |  | identity |
| ShoppingCartID | nvarchar(50) |  |  |
| Quantity | int |  | default `((1))` |
| ProductID | int |  |  |
| DateCreated | datetime |  | default `(getdate())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID)

Indexes: `PK_ShoppingCartItem_ShoppingCartItemID` clustered unique (ShoppingCartItemID); `IX_ShoppingCartItem_ShoppingCartID_ProductID` nonclustered (ShoppingCartID, ProductID)

#### Sales.SpecialOffer — 16 rows

PK: `SpecialOfferID`

| Column | Type | Null | Notes |
|---|---|---|---|
| SpecialOfferID | int |  | identity |
| Description | nvarchar(255) |  |  |
| DiscountPct | smallmoney |  | default `((0.00))` |
| Type | nvarchar(50) |  |  |
| Category | nvarchar(50) |  |  |
| StartDate | datetime |  |  |
| EndDate | datetime |  |  |
| MinQty | int |  | default `((0))` |
| MaxQty | int | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_SpecialOffer_SpecialOfferID` clustered unique (SpecialOfferID); `AK_SpecialOffer_rowguid` nonclustered unique (rowguid)

#### Sales.SpecialOfferProduct — 538 rows

PK: `SpecialOfferID, ProductID`

| Column | Type | Null | Notes |
|---|---|---|---|
| SpecialOfferID | int |  |  |
| ProductID | int |  |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (ProductID) → Production.Product(ProductID); (SpecialOfferID) → Sales.SpecialOffer(SpecialOfferID)

Indexes: `PK_SpecialOfferProduct_SpecialOfferID_ProductID` clustered unique (SpecialOfferID, ProductID); `AK_SpecialOfferProduct_rowguid` nonclustered unique (rowguid); `IX_SpecialOfferProduct_ProductID` nonclustered (ProductID)

#### Sales.Store — 701 rows

PK: `BusinessEntityID`

| Column | Type | Null | Notes |
|---|---|---|---|
| BusinessEntityID | int |  |  |
| Name | Name |  |  |
| SalesPersonID | int | Y |  |
| Demographics | xml | Y |  |
| rowguid | uniqueidentifier |  | default `(newid())` |
| ModifiedDate | datetime |  | default `(getdate())` |

FKs: (BusinessEntityID) → Person.BusinessEntity(BusinessEntityID); (SalesPersonID) → Sales.SalesPerson(BusinessEntityID)

Indexes: `PK_Store_BusinessEntityID` clustered unique (BusinessEntityID); `AK_Store_rowguid` nonclustered unique (rowguid); `IX_Store_SalesPersonID` nonclustered (SalesPersonID); `PXML_Store_Demographics` xml (Demographics)

#### dbo.AWBuildVersion — 1 rows

PK: `SystemInformationID`

| Column | Type | Null | Notes |
|---|---|---|---|
| SystemInformationID | tinyint |  | identity |
| Database Version | nvarchar(25) |  |  |
| VersionDate | datetime |  |  |
| ModifiedDate | datetime |  | default `(getdate())` |

Indexes: `PK_AWBuildVersion_SystemInformationID` clustered unique (SystemInformationID)

#### dbo.DatabaseLog — 1,596 rows

PK: `DatabaseLogID`

| Column | Type | Null | Notes |
|---|---|---|---|
| DatabaseLogID | int |  | identity |
| PostTime | datetime |  |  |
| DatabaseUser | sysname |  |  |
| Event | sysname |  |  |
| Schema | sysname | Y |  |
| Object | sysname | Y |  |
| TSQL | nvarchar(max) |  |  |
| XmlEvent | xml |  |  |

Indexes: `PK_DatabaseLog_DatabaseLogID` nonclustered unique (DatabaseLogID)

#### dbo.ErrorLog — 0 rows

PK: `ErrorLogID`

| Column | Type | Null | Notes |
|---|---|---|---|
| ErrorLogID | int |  | identity |
| ErrorTime | datetime |  | default `(getdate())` |
| UserName | sysname |  |  |
| ErrorNumber | int |  |  |
| ErrorSeverity | int | Y |  |
| ErrorState | int | Y |  |
| ErrorProcedure | nvarchar(126) | Y |  |
| ErrorLine | int | Y |  |
| ErrorMessage | nvarchar(4000) |  |  |

Indexes: `PK_ErrorLog_ErrorLogID` clustered unique (ErrorLogID)

## AdventureWorksDW2022

### Tables per schema

| Schema | Tables | Rows | Tables (rows) |
|---|---|---|---|
| dbo | 30 | 1,060,811 | AdventureWorksDWBuildVersion (1), DatabaseLog (96), DimAccount (99), DimCurrency (105), DimCustomer (18,484), DimDate (3,652), DimDepartmentGroup (7), DimEmployee (296), DimGeography (655), DimOrganization (14), DimProduct (606), DimProductCategory (4), DimProductSubcategory (37), DimPromotion (16), DimReseller (701), DimSalesReason (10), DimSalesTerritory (11), DimScenario (3), FactAdditionalInternationalProductDescription (15,168), FactCallCenter (120), FactCurrencyRate (14,264), FactFinance (39,409), FactInternetSales (60,398), FactInternetSalesReason (64,515), FactProductInventory (776,286), FactResellerSales (60,855), FactSalesQuota (163), FactSurveyResponse (2,727), NewFactCurrencyRate (50), ProspectiveBuyer (2,059) |

### Views (5)

| Name | Type | References |
|---|---|---|
| dbo.vAssocSeqLineItems | VIEW | dbo.vDMPrep |
| dbo.vAssocSeqOrders | VIEW | dbo.vDMPrep |
| dbo.vDMPrep | VIEW | dbo.DimCustomer, dbo.DimDate, dbo.DimGeography, dbo.DimProduct, dbo.DimProductCategory, dbo.DimProductSubcategory, dbo.DimSalesTerritory, dbo.FactInternetSales |
| dbo.vTargetMail | VIEW | dbo.DimCustomer, dbo.vDMPrep |
| dbo.vTimeSeries | VIEW | dbo.udfBuildISO8601Date, dbo.vDMPrep |

### Functions (3)

| Name | Type | References |
|---|---|---|
| dbo.udfBuildISO8601Date | SQL_SCALAR_FUNCTION | dbo.udfTwoDigitZeroFill |
| dbo.udfMinimumDate | SQL_SCALAR_FUNCTION |  |
| dbo.udfTwoDigitZeroFill | SQL_SCALAR_FUNCTION |  |

### Triggers (1)

| Trigger | On |
|---|---|
| ddlDatabaseTriggerLog | DATABASE |

### Table details

#### dbo.AdventureWorksDWBuildVersion — 1 rows

PK: _none_

| Column | Type | Null | Notes |
|---|---|---|---|
| DBVersion | nvarchar(50) | Y |  |
| VersionDate | datetime | Y |  |

#### dbo.DatabaseLog — 96 rows

PK: `DatabaseLogID`

| Column | Type | Null | Notes |
|---|---|---|---|
| DatabaseLogID | int |  | identity |
| PostTime | datetime |  |  |
| DatabaseUser | sysname |  |  |
| Event | sysname |  |  |
| Schema | sysname | Y |  |
| Object | sysname | Y |  |
| TSQL | nvarchar(max) |  |  |
| XmlEvent | xml |  |  |

Indexes: `PK_DatabaseLog_DatabaseLogID` nonclustered unique (DatabaseLogID)

#### dbo.DimAccount — 99 rows

PK: `AccountKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| AccountKey | int |  | identity |
| ParentAccountKey | int | Y |  |
| AccountCodeAlternateKey | int | Y |  |
| ParentAccountCodeAlternateKey | int | Y |  |
| AccountDescription | nvarchar(50) | Y |  |
| AccountType | nvarchar(50) | Y |  |
| Operator | nvarchar(50) | Y |  |
| CustomMembers | nvarchar(300) | Y |  |
| ValueType | nvarchar(50) | Y |  |
| CustomMemberOptions | nvarchar(200) | Y |  |

FKs: (ParentAccountKey) → dbo.DimAccount(AccountKey)

Indexes: `PK_DimAccount` clustered unique (AccountKey)

#### dbo.DimCurrency — 105 rows

PK: `CurrencyKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| CurrencyKey | int |  | identity |
| CurrencyAlternateKey | nchar(3) |  |  |
| CurrencyName | nvarchar(50) |  |  |

Indexes: `PK_DimCurrency_CurrencyKey` clustered unique (CurrencyKey); `AK_DimCurrency_CurrencyAlternateKey` nonclustered unique (CurrencyAlternateKey)

#### dbo.DimCustomer — 18,484 rows

PK: `CustomerKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| CustomerKey | int |  | identity |
| GeographyKey | int | Y |  |
| CustomerAlternateKey | nvarchar(15) |  |  |
| Title | nvarchar(8) | Y |  |
| FirstName | nvarchar(50) | Y |  |
| MiddleName | nvarchar(50) | Y |  |
| LastName | nvarchar(50) | Y |  |
| NameStyle | bit | Y |  |
| BirthDate | date | Y |  |
| MaritalStatus | nchar(1) | Y |  |
| Suffix | nvarchar(10) | Y |  |
| Gender | nvarchar(1) | Y |  |
| EmailAddress | nvarchar(50) | Y |  |
| YearlyIncome | money | Y |  |
| TotalChildren | tinyint | Y |  |
| NumberChildrenAtHome | tinyint | Y |  |
| EnglishEducation | nvarchar(40) | Y |  |
| SpanishEducation | nvarchar(40) | Y |  |
| FrenchEducation | nvarchar(40) | Y |  |
| EnglishOccupation | nvarchar(100) | Y |  |
| SpanishOccupation | nvarchar(100) | Y |  |
| FrenchOccupation | nvarchar(100) | Y |  |
| HouseOwnerFlag | nchar(1) | Y |  |
| NumberCarsOwned | tinyint | Y |  |
| AddressLine1 | nvarchar(120) | Y |  |
| AddressLine2 | nvarchar(120) | Y |  |
| Phone | nvarchar(20) | Y |  |
| DateFirstPurchase | date | Y |  |
| CommuteDistance | nvarchar(15) | Y |  |

FKs: (GeographyKey) → dbo.DimGeography(GeographyKey)

Indexes: `PK_DimCustomer_CustomerKey` clustered unique (CustomerKey); `IX_DimCustomer_CustomerAlternateKey` nonclustered unique (CustomerAlternateKey)

#### dbo.DimDate — 3,652 rows

PK: `DateKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| DateKey | int |  |  |
| FullDateAlternateKey | date |  |  |
| DayNumberOfWeek | tinyint |  |  |
| EnglishDayNameOfWeek | nvarchar(10) |  |  |
| SpanishDayNameOfWeek | nvarchar(10) |  |  |
| FrenchDayNameOfWeek | nvarchar(10) |  |  |
| DayNumberOfMonth | tinyint |  |  |
| DayNumberOfYear | smallint |  |  |
| WeekNumberOfYear | tinyint |  |  |
| EnglishMonthName | nvarchar(10) |  |  |
| SpanishMonthName | nvarchar(10) |  |  |
| FrenchMonthName | nvarchar(10) |  |  |
| MonthNumberOfYear | tinyint |  |  |
| CalendarQuarter | tinyint |  |  |
| CalendarYear | smallint |  |  |
| CalendarSemester | tinyint |  |  |
| FiscalQuarter | tinyint |  |  |
| FiscalYear | smallint |  |  |
| FiscalSemester | tinyint |  |  |

Indexes: `PK_DimDate_DateKey` clustered unique (DateKey); `AK_DimDate_FullDateAlternateKey` nonclustered unique (FullDateAlternateKey)

#### dbo.DimDepartmentGroup — 7 rows

PK: `DepartmentGroupKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| DepartmentGroupKey | int |  | identity |
| ParentDepartmentGroupKey | int | Y |  |
| DepartmentGroupName | nvarchar(50) | Y |  |

FKs: (ParentDepartmentGroupKey) → dbo.DimDepartmentGroup(DepartmentGroupKey)

Indexes: `PK_DimDepartmentGroup` clustered unique (DepartmentGroupKey)

#### dbo.DimEmployee — 296 rows

PK: `EmployeeKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| EmployeeKey | int |  | identity |
| ParentEmployeeKey | int | Y |  |
| EmployeeNationalIDAlternateKey | nvarchar(15) | Y |  |
| ParentEmployeeNationalIDAlternateKey | nvarchar(15) | Y |  |
| SalesTerritoryKey | int | Y |  |
| FirstName | nvarchar(50) |  |  |
| LastName | nvarchar(50) |  |  |
| MiddleName | nvarchar(50) | Y |  |
| NameStyle | bit |  |  |
| Title | nvarchar(50) | Y |  |
| HireDate | date | Y |  |
| BirthDate | date | Y |  |
| LoginID | nvarchar(256) | Y |  |
| EmailAddress | nvarchar(50) | Y |  |
| Phone | nvarchar(25) | Y |  |
| MaritalStatus | nchar(1) | Y |  |
| EmergencyContactName | nvarchar(50) | Y |  |
| EmergencyContactPhone | nvarchar(25) | Y |  |
| SalariedFlag | bit | Y |  |
| Gender | nchar(1) | Y |  |
| PayFrequency | tinyint | Y |  |
| BaseRate | money | Y |  |
| VacationHours | smallint | Y |  |
| SickLeaveHours | smallint | Y |  |
| CurrentFlag | bit |  |  |
| SalesPersonFlag | bit |  |  |
| DepartmentName | nvarchar(50) | Y |  |
| StartDate | date | Y |  |
| EndDate | date | Y |  |
| Status | nvarchar(50) | Y |  |
| EmployeePhoto | varbinary(max) | Y |  |

FKs: (SalesTerritoryKey) → dbo.DimSalesTerritory(SalesTerritoryKey); (ParentEmployeeKey) → dbo.DimEmployee(EmployeeKey)

Indexes: `PK_DimEmployee_EmployeeKey` clustered unique (EmployeeKey)

#### dbo.DimGeography — 655 rows

PK: `GeographyKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| GeographyKey | int |  | identity |
| City | nvarchar(30) | Y |  |
| StateProvinceCode | nvarchar(3) | Y |  |
| StateProvinceName | nvarchar(50) | Y |  |
| CountryRegionCode | nvarchar(3) | Y |  |
| EnglishCountryRegionName | nvarchar(50) | Y |  |
| SpanishCountryRegionName | nvarchar(50) | Y |  |
| FrenchCountryRegionName | nvarchar(50) | Y |  |
| PostalCode | nvarchar(15) | Y |  |
| SalesTerritoryKey | int | Y |  |
| IpAddressLocator | nvarchar(15) | Y |  |

FKs: (SalesTerritoryKey) → dbo.DimSalesTerritory(SalesTerritoryKey)

Indexes: `PK_DimGeography_GeographyKey` clustered unique (GeographyKey)

#### dbo.DimOrganization — 14 rows

PK: `OrganizationKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| OrganizationKey | int |  | identity |
| ParentOrganizationKey | int | Y |  |
| PercentageOfOwnership | nvarchar(16) | Y |  |
| OrganizationName | nvarchar(50) | Y |  |
| CurrencyKey | int | Y |  |

FKs: (CurrencyKey) → dbo.DimCurrency(CurrencyKey); (ParentOrganizationKey) → dbo.DimOrganization(OrganizationKey)

Indexes: `PK_DimOrganization` clustered unique (OrganizationKey)

#### dbo.DimProduct — 606 rows

PK: `ProductKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductKey | int |  | identity |
| ProductAlternateKey | nvarchar(25) | Y |  |
| ProductSubcategoryKey | int | Y |  |
| WeightUnitMeasureCode | nchar(3) | Y |  |
| SizeUnitMeasureCode | nchar(3) | Y |  |
| EnglishProductName | nvarchar(50) |  |  |
| SpanishProductName | nvarchar(50) |  |  |
| FrenchProductName | nvarchar(50) |  |  |
| StandardCost | money | Y |  |
| FinishedGoodsFlag | bit |  |  |
| Color | nvarchar(15) |  |  |
| SafetyStockLevel | smallint | Y |  |
| ReorderPoint | smallint | Y |  |
| ListPrice | money | Y |  |
| Size | nvarchar(50) | Y |  |
| SizeRange | nvarchar(50) | Y |  |
| Weight | float | Y |  |
| DaysToManufacture | int | Y |  |
| ProductLine | nchar(2) | Y |  |
| DealerPrice | money | Y |  |
| Class | nchar(2) | Y |  |
| Style | nchar(2) | Y |  |
| ModelName | nvarchar(50) | Y |  |
| LargePhoto | varbinary(max) | Y |  |
| EnglishDescription | nvarchar(400) | Y |  |
| FrenchDescription | nvarchar(400) | Y |  |
| ChineseDescription | nvarchar(400) | Y |  |
| ArabicDescription | nvarchar(400) | Y |  |
| HebrewDescription | nvarchar(400) | Y |  |
| ThaiDescription | nvarchar(400) | Y |  |
| GermanDescription | nvarchar(400) | Y |  |
| JapaneseDescription | nvarchar(400) | Y |  |
| TurkishDescription | nvarchar(400) | Y |  |
| StartDate | datetime | Y |  |
| EndDate | datetime | Y |  |
| Status | nvarchar(7) | Y |  |

FKs: (ProductSubcategoryKey) → dbo.DimProductSubcategory(ProductSubcategoryKey)

Indexes: `PK_DimProduct_ProductKey` clustered unique (ProductKey); `AK_DimProduct_ProductAlternateKey_StartDate` nonclustered unique (ProductAlternateKey, StartDate)

#### dbo.DimProductCategory — 4 rows

PK: `ProductCategoryKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductCategoryKey | int |  | identity |
| ProductCategoryAlternateKey | int | Y |  |
| EnglishProductCategoryName | nvarchar(50) |  |  |
| SpanishProductCategoryName | nvarchar(50) |  |  |
| FrenchProductCategoryName | nvarchar(50) |  |  |

Indexes: `PK_DimProductCategory_ProductCategoryKey` clustered unique (ProductCategoryKey); `AK_DimProductCategory_ProductCategoryAlternateKey` nonclustered unique (ProductCategoryAlternateKey)

#### dbo.DimProductSubcategory — 37 rows

PK: `ProductSubcategoryKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductSubcategoryKey | int |  | identity |
| ProductSubcategoryAlternateKey | int | Y |  |
| EnglishProductSubcategoryName | nvarchar(50) |  |  |
| SpanishProductSubcategoryName | nvarchar(50) |  |  |
| FrenchProductSubcategoryName | nvarchar(50) |  |  |
| ProductCategoryKey | int | Y |  |

FKs: (ProductCategoryKey) → dbo.DimProductCategory(ProductCategoryKey)

Indexes: `PK_DimProductSubcategory_ProductSubcategoryKey` clustered unique (ProductSubcategoryKey); `AK_DimProductSubcategory_ProductSubcategoryAlternateKey` nonclustered unique (ProductSubcategoryAlternateKey)

#### dbo.DimPromotion — 16 rows

PK: `PromotionKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| PromotionKey | int |  | identity |
| PromotionAlternateKey | int | Y |  |
| EnglishPromotionName | nvarchar(255) | Y |  |
| SpanishPromotionName | nvarchar(255) | Y |  |
| FrenchPromotionName | nvarchar(255) | Y |  |
| DiscountPct | float | Y |  |
| EnglishPromotionType | nvarchar(50) | Y |  |
| SpanishPromotionType | nvarchar(50) | Y |  |
| FrenchPromotionType | nvarchar(50) | Y |  |
| EnglishPromotionCategory | nvarchar(50) | Y |  |
| SpanishPromotionCategory | nvarchar(50) | Y |  |
| FrenchPromotionCategory | nvarchar(50) | Y |  |
| StartDate | datetime |  |  |
| EndDate | datetime | Y |  |
| MinQty | int | Y |  |
| MaxQty | int | Y |  |

Indexes: `PK_DimPromotion_PromotionKey` clustered unique (PromotionKey); `AK_DimPromotion_PromotionAlternateKey` nonclustered unique (PromotionAlternateKey)

#### dbo.DimReseller — 701 rows

PK: `ResellerKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| ResellerKey | int |  | identity |
| GeographyKey | int | Y |  |
| ResellerAlternateKey | nvarchar(15) | Y |  |
| Phone | nvarchar(25) | Y |  |
| BusinessType | varchar(20) |  |  |
| ResellerName | nvarchar(50) |  |  |
| NumberEmployees | int | Y |  |
| OrderFrequency | char(1) | Y |  |
| OrderMonth | tinyint | Y |  |
| FirstOrderYear | int | Y |  |
| LastOrderYear | int | Y |  |
| ProductLine | nvarchar(50) | Y |  |
| AddressLine1 | nvarchar(60) | Y |  |
| AddressLine2 | nvarchar(60) | Y |  |
| AnnualSales | money | Y |  |
| BankName | nvarchar(50) | Y |  |
| MinPaymentType | tinyint | Y |  |
| MinPaymentAmount | money | Y |  |
| AnnualRevenue | money | Y |  |
| YearOpened | int | Y |  |

FKs: (GeographyKey) → dbo.DimGeography(GeographyKey)

Indexes: `PK_DimReseller_ResellerKey` clustered unique (ResellerKey); `AK_DimReseller_ResellerAlternateKey` nonclustered unique (ResellerAlternateKey)

#### dbo.DimSalesReason — 10 rows

PK: `SalesReasonKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| SalesReasonKey | int |  | identity |
| SalesReasonAlternateKey | int |  |  |
| SalesReasonName | nvarchar(50) |  |  |
| SalesReasonReasonType | nvarchar(50) |  |  |

Indexes: `PK_DimSalesReason_SalesReasonKey` clustered unique (SalesReasonKey)

#### dbo.DimSalesTerritory — 11 rows

PK: `SalesTerritoryKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| SalesTerritoryKey | int |  | identity |
| SalesTerritoryAlternateKey | int | Y |  |
| SalesTerritoryRegion | nvarchar(50) |  |  |
| SalesTerritoryCountry | nvarchar(50) |  |  |
| SalesTerritoryGroup | nvarchar(50) | Y |  |
| SalesTerritoryImage | varbinary(max) | Y |  |

Indexes: `PK_DimSalesTerritory_SalesTerritoryKey` clustered unique (SalesTerritoryKey); `AK_DimSalesTerritory_SalesTerritoryAlternateKey` nonclustered unique (SalesTerritoryAlternateKey)

#### dbo.DimScenario — 3 rows

PK: `ScenarioKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| ScenarioKey | int |  | identity |
| ScenarioName | nvarchar(50) | Y |  |

Indexes: `PK_DimScenario` clustered unique (ScenarioKey)

#### dbo.FactAdditionalInternationalProductDescription — 15,168 rows

PK: `ProductKey, CultureName`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductKey | int |  |  |
| CultureName | nvarchar(50) |  |  |
| ProductDescription | nvarchar(max) |  |  |

Indexes: `PK_FactAdditionalInternationalProductDescription_ProductKey_CultureName` clustered unique (ProductKey, CultureName)

#### dbo.FactCallCenter — 120 rows

PK: `FactCallCenterID`

| Column | Type | Null | Notes |
|---|---|---|---|
| FactCallCenterID | int |  | identity |
| DateKey | int |  |  |
| WageType | nvarchar(15) |  |  |
| Shift | nvarchar(20) |  |  |
| LevelOneOperators | smallint |  |  |
| LevelTwoOperators | smallint |  |  |
| TotalOperators | smallint |  |  |
| Calls | int |  |  |
| AutomaticResponses | int |  |  |
| Orders | int |  |  |
| IssuesRaised | smallint |  |  |
| AverageTimePerIssue | smallint |  |  |
| ServiceGrade | float |  |  |
| Date | datetime | Y |  |

FKs: (DateKey) → dbo.DimDate(DateKey)

Indexes: `PK_FactCallCenter_FactCallCenterID` clustered unique (FactCallCenterID); `AK_FactCallCenter_DateKey_Shift` nonclustered unique (DateKey, Shift)

#### dbo.FactCurrencyRate — 14,264 rows

PK: `CurrencyKey, DateKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| CurrencyKey | int |  |  |
| DateKey | int |  |  |
| AverageRate | float |  |  |
| EndOfDayRate | float |  |  |
| Date | datetime | Y |  |

FKs: (DateKey) → dbo.DimDate(DateKey); (CurrencyKey) → dbo.DimCurrency(CurrencyKey)

Indexes: `PK_FactCurrencyRate_CurrencyKey_DateKey` clustered unique (CurrencyKey, DateKey)

#### dbo.FactFinance — 39,409 rows

PK: _none_

| Column | Type | Null | Notes |
|---|---|---|---|
| FinanceKey | int |  | identity |
| DateKey | int |  |  |
| OrganizationKey | int |  |  |
| DepartmentGroupKey | int |  |  |
| ScenarioKey | int |  |  |
| AccountKey | int |  |  |
| Amount | float |  |  |
| Date | datetime | Y |  |

FKs: (ScenarioKey) → dbo.DimScenario(ScenarioKey); (OrganizationKey) → dbo.DimOrganization(OrganizationKey); (DepartmentGroupKey) → dbo.DimDepartmentGroup(DepartmentGroupKey); (DateKey) → dbo.DimDate(DateKey); (AccountKey) → dbo.DimAccount(AccountKey)

#### dbo.FactInternetSales — 60,398 rows

PK: `SalesOrderNumber, SalesOrderLineNumber`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductKey | int |  |  |
| OrderDateKey | int |  |  |
| DueDateKey | int |  |  |
| ShipDateKey | int |  |  |
| CustomerKey | int |  |  |
| PromotionKey | int |  |  |
| CurrencyKey | int |  |  |
| SalesTerritoryKey | int |  |  |
| SalesOrderNumber | nvarchar(20) |  |  |
| SalesOrderLineNumber | tinyint |  |  |
| RevisionNumber | tinyint |  |  |
| OrderQuantity | smallint |  |  |
| UnitPrice | money |  |  |
| ExtendedAmount | money |  |  |
| UnitPriceDiscountPct | float |  |  |
| DiscountAmount | float |  |  |
| ProductStandardCost | money |  |  |
| TotalProductCost | money |  |  |
| SalesAmount | money |  |  |
| TaxAmt | money |  |  |
| Freight | money |  |  |
| CarrierTrackingNumber | nvarchar(25) | Y |  |
| CustomerPONumber | nvarchar(25) | Y |  |
| OrderDate | datetime | Y |  |
| DueDate | datetime | Y |  |
| ShipDate | datetime | Y |  |

FKs: (CurrencyKey) → dbo.DimCurrency(CurrencyKey); (CustomerKey) → dbo.DimCustomer(CustomerKey); (OrderDateKey) → dbo.DimDate(DateKey); (DueDateKey) → dbo.DimDate(DateKey); (ShipDateKey) → dbo.DimDate(DateKey); (ProductKey) → dbo.DimProduct(ProductKey); (PromotionKey) → dbo.DimPromotion(PromotionKey); (SalesTerritoryKey) → dbo.DimSalesTerritory(SalesTerritoryKey)

Indexes: `PK_FactInternetSales_SalesOrderNumber_SalesOrderLineNumber` clustered unique (SalesOrderNumber, SalesOrderLineNumber)

#### dbo.FactInternetSalesReason — 64,515 rows

PK: `SalesOrderNumber, SalesOrderLineNumber, SalesReasonKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| SalesOrderNumber | nvarchar(20) |  |  |
| SalesOrderLineNumber | tinyint |  |  |
| SalesReasonKey | int |  |  |

FKs: (SalesOrderNumber, SalesOrderLineNumber) → dbo.FactInternetSales(SalesOrderNumber, SalesOrderLineNumber); (SalesReasonKey) → dbo.DimSalesReason(SalesReasonKey)

Indexes: `PK_FactInternetSalesReason_SalesOrderNumber_SalesOrderLineNumber_SalesReasonKey` clustered unique (SalesOrderNumber, SalesOrderLineNumber, SalesReasonKey)

#### dbo.FactProductInventory — 776,286 rows

PK: `ProductKey, DateKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductKey | int |  |  |
| DateKey | int |  |  |
| MovementDate | date |  |  |
| UnitCost | money |  |  |
| UnitsIn | int |  |  |
| UnitsOut | int |  |  |
| UnitsBalance | int |  |  |

FKs: (DateKey) → dbo.DimDate(DateKey); (ProductKey) → dbo.DimProduct(ProductKey)

Indexes: `PK_FactProductInventory` clustered unique (ProductKey, DateKey)

#### dbo.FactResellerSales — 60,855 rows

PK: `SalesOrderNumber, SalesOrderLineNumber`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProductKey | int |  |  |
| OrderDateKey | int |  |  |
| DueDateKey | int |  |  |
| ShipDateKey | int |  |  |
| ResellerKey | int |  |  |
| EmployeeKey | int |  |  |
| PromotionKey | int |  |  |
| CurrencyKey | int |  |  |
| SalesTerritoryKey | int |  |  |
| SalesOrderNumber | nvarchar(20) |  |  |
| SalesOrderLineNumber | tinyint |  |  |
| RevisionNumber | tinyint | Y |  |
| OrderQuantity | smallint | Y |  |
| UnitPrice | money | Y |  |
| ExtendedAmount | money | Y |  |
| UnitPriceDiscountPct | float | Y |  |
| DiscountAmount | float | Y |  |
| ProductStandardCost | money | Y |  |
| TotalProductCost | money | Y |  |
| SalesAmount | money | Y |  |
| TaxAmt | money | Y |  |
| Freight | money | Y |  |
| CarrierTrackingNumber | nvarchar(25) | Y |  |
| CustomerPONumber | nvarchar(25) | Y |  |
| OrderDate | datetime | Y |  |
| DueDate | datetime | Y |  |
| ShipDate | datetime | Y |  |

FKs: (CurrencyKey) → dbo.DimCurrency(CurrencyKey); (OrderDateKey) → dbo.DimDate(DateKey); (DueDateKey) → dbo.DimDate(DateKey); (ShipDateKey) → dbo.DimDate(DateKey); (EmployeeKey) → dbo.DimEmployee(EmployeeKey); (ProductKey) → dbo.DimProduct(ProductKey); (PromotionKey) → dbo.DimPromotion(PromotionKey); (ResellerKey) → dbo.DimReseller(ResellerKey); (SalesTerritoryKey) → dbo.DimSalesTerritory(SalesTerritoryKey)

Indexes: `PK_FactResellerSales_SalesOrderNumber_SalesOrderLineNumber` clustered unique (SalesOrderNumber, SalesOrderLineNumber)

#### dbo.FactSalesQuota — 163 rows

PK: `SalesQuotaKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| SalesQuotaKey | int |  | identity |
| EmployeeKey | int |  |  |
| DateKey | int |  |  |
| CalendarYear | smallint |  |  |
| CalendarQuarter | tinyint |  |  |
| SalesAmountQuota | money |  |  |
| Date | datetime | Y |  |

FKs: (EmployeeKey) → dbo.DimEmployee(EmployeeKey); (DateKey) → dbo.DimDate(DateKey)

Indexes: `PK_FactSalesQuota_SalesQuotaKey` clustered unique (SalesQuotaKey)

#### dbo.FactSurveyResponse — 2,727 rows

PK: `SurveyResponseKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| SurveyResponseKey | int |  | identity |
| DateKey | int |  |  |
| CustomerKey | int |  |  |
| ProductCategoryKey | int |  |  |
| EnglishProductCategoryName | nvarchar(50) |  |  |
| ProductSubcategoryKey | int |  |  |
| EnglishProductSubcategoryName | nvarchar(50) |  |  |
| Date | datetime | Y |  |

FKs: (DateKey) → dbo.DimDate(DateKey); (CustomerKey) → dbo.DimCustomer(CustomerKey)

Indexes: `PK_FactSurveyResponse_SurveyResponseKey` clustered unique (SurveyResponseKey)

#### dbo.NewFactCurrencyRate — 50 rows

PK: _none_

| Column | Type | Null | Notes |
|---|---|---|---|
| AverageRate | real | Y |  |
| CurrencyID | nvarchar(3) | Y |  |
| CurrencyDate | date | Y |  |
| EndOfDayRate | real | Y |  |
| CurrencyKey | int | Y |  |
| DateKey | int | Y |  |

#### dbo.ProspectiveBuyer — 2,059 rows

PK: `ProspectiveBuyerKey`

| Column | Type | Null | Notes |
|---|---|---|---|
| ProspectiveBuyerKey | int |  | identity |
| ProspectAlternateKey | nvarchar(15) | Y |  |
| FirstName | nvarchar(50) | Y |  |
| MiddleName | nvarchar(50) | Y |  |
| LastName | nvarchar(50) | Y |  |
| BirthDate | datetime | Y |  |
| MaritalStatus | nchar(1) | Y |  |
| Gender | nvarchar(1) | Y |  |
| EmailAddress | nvarchar(50) | Y |  |
| YearlyIncome | money | Y |  |
| TotalChildren | tinyint | Y |  |
| NumberChildrenAtHome | tinyint | Y |  |
| Education | nvarchar(40) | Y |  |
| Occupation | nvarchar(100) | Y |  |
| HouseOwnerFlag | nchar(1) | Y |  |
| NumberCarsOwned | tinyint | Y |  |
| AddressLine1 | nvarchar(120) | Y |  |
| AddressLine2 | nvarchar(120) | Y |  |
| City | nvarchar(30) | Y |  |
| StateProvinceCode | nvarchar(3) | Y |  |
| PostalCode | nvarchar(15) | Y |  |
| Phone | nvarchar(20) | Y |  |
| Salutation | nvarchar(8) | Y |  |
| Unknown | int | Y |  |

Indexes: `PK_ProspectiveBuyer_ProspectiveBuyerKey` clustered unique (ProspectiveBuyerKey)

