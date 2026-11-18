"""Saved report operations observed in Monarch web v1.0.6163 (2026-11-15)."""

from graphql import parse

_FIELDS = """
fragment TransactionFilterSetFields on TransactionFilterSet {
  id
  displayName
  categories {
    id
    name
    icon
  }
  excludedCategories {
    id
    name
    icon
  }
  categoryGroups {
    id
    name
    type
  }
  excludedCategoryGroups {
    id
    name
    type
  }
  accounts {
    id
    displayName
    logoUrl
    icon
  }
  excludedAccounts {
    id
    displayName
    logoUrl
    icon
  }
  merchants {
    id
    name
    logoUrl
  }
  excludedMerchants {
    id
    name
    logoUrl
  }
  tags {
    id
    name
    color
  }
  tagMatchMode
  excludedTags {
    id
    name
    color
  }
  excludeTagMatchMode
  isUntagged
  goals {
    id
    name
    imageStorageProvider
    imageStorageProviderId
  }
  excludedGoals {
    id
    name
    imageStorageProvider
    imageStorageProviderId
  }
  savingsGoals {
    id
    name
    imageStorageProvider
    imageStorageProviderId
  }
  excludedSavingsGoals {
    id
    name
    imageStorageProvider
    imageStorageProviderId
  }
  searchQuery
  systemCategories
  systemCategoryGroups
  categoryType
  isUncategorized
  budgetVariability
  isFlexSpending
  startDate
  endDate
  timeframePeriod {
    unit
    value
    includeCurrent
  }
  createdBefore
  createdAfter
  absAmountGte
  absAmountLte
  isSplit
  isRecurring
  isInvestmentAccount
  isPending
  creditsOnly
  debitsOnly
  hasNotes
  hasAttachments
  hiddenFromReports
  importedFromMint
  syncedFromInstitution
  needsReview
  needsReviewUnassigned
  needsReviewByUser {
    id
    name
  }
  ownershipSet {
    includeJointlyOwned
    users {
      id
      name
      profilePictureUrl
    }
    excludedUsers {
      id
      name
      profilePictureUrl
    }
  }
  businessEntitySet {
    includeUnassigned
    businessEntities {
      id
      name
      logoUrl
      color
    }
    excludedBusinessEntities {
      id
      name
      logoUrl
      color
    }
  }
}

fragment ReportConfigurationFields on ReportConfiguration {
  id
  displayName
  transactionFilterSet {
    ...TransactionFilterSetFields
  }
  reportView {
    analysisScope
    chartType
    chartCalculation
    chartLayout
    chartDensity
    dimensions
    timeframe
  }
}
"""

GET_REPORTS = parse(
    """
query Common_GetReportConfigurations { reportConfigurations { ...ReportConfigurationFields } }
"""
    + _FIELDS
)

CREATE_REPORTS = parse(
    """
mutation Common_CreateReportConfiguration($input: CreateReportConfigurationInput!) {
  createReportConfiguration(input: $input) {
    reportConfiguration { ...ReportConfigurationFields }
    errors { message code fieldErrors { field messages } }
  }
}
"""
    + _FIELDS
)

UPDATE_REPORTS = parse(
    """
mutation Common_UpdateReportConfiguration($input: UpdateReportConfigurationInput!) {
  updateReportConfiguration(input: $input) {
    reportConfiguration { ...ReportConfigurationFields }
    errors { message code fieldErrors { field messages } }
  }
}
"""
    + _FIELDS
)

DELETE_REPORT = parse("""
mutation Common_DeleteReportConfiguration($id: ID!) {
  deleteReportConfiguration(id: $id) {
    deleted
    errors { message code fieldErrors { field messages } }
  }
}
""")
