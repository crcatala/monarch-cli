"""Observed Monarch web receipt operations (v1.0.6163, November 15, 2026).

See docs/receipt-api.md for provenance. These are private GraphQL operations.
"""

from graphql import parse

# Shared selection from Common_RetailSyncQuery and Common_RetailSyncsQueryWithTotal.
_RECEIPT_FIELDS = """
fragment ReceiptFields on RetailSync {
  id vendor status startedAt endedAt createdAt updatedAt
  attachments {
    id filename extension sizeBytes originalAssetUrl thumbnailUrl isGeneratedReceiptImage
  }
  orders {
    id merchantName vendor vendorOrderId inStorePurchase date grandTotal
    totalForProducts shipping deliveryFee additionalCharges adjustmentsAmount
    totalBeforeTax tax tip giftCardAmount displayStatus
    retailLineItems { ...ReceiptLineItemFields }
    retailTransactions {
      id date total transactionType transactionUpdateSkipped
      transaction {
        id amount isManual hasSplitTransactions pending
        category { id name icon }
        merchant { id name logoUrl }
        splitTransactions {
          id amount date pending
          category { id name icon }
          merchant { id name logoUrl }
        }
      }
      lineItems { ...ReceiptLineItemFields }
    }
  }
}
fragment ReceiptLineItemFields on RetailLineItem {
  id title quantity price total isAssociatedToRetailTransaction
  category { id name icon }
}
"""

INBOX_QUERY = parse(
    """
query Common_RetailSyncsQueryWithTotal(
  $filters: RetailSyncFilterInput!, $offset: Int!, $limit: Int!,
  $includeTotalCount: Boolean, $orderBy: RetailSyncOrdering!
) {
  retailSyncsWithTotal(
    filters: $filters, offset: $offset, limit: $limit,
    includeTotalCount: $includeTotalCount, orderBy: $orderBy
  ) { totalCount results { ...ReceiptFields } }
}
"""
    + _RECEIPT_FIELDS
)

RECEIPT_QUERY = parse(
    """
query Common_RetailSyncQuery($syncId: ID!) {
  retailSync(id: $syncId) { ...ReceiptFields }
}
"""
    + _RECEIPT_FIELDS
)

MATCH_MUTATION = parse("""
mutation Common_MatchRetailTransaction($retailTransactionId: ID!, $transactionId: ID!) {
  matchRetailTransaction(
    retailTransactionId: $retailTransactionId, transactionId: $transactionId
  ) {
    retailSync { id status }
    errors { message code fieldErrors { field messages } }
  }
}
""")
