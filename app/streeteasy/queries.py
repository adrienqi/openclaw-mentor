"""GraphQL documents for api-v6.streeteasy.com (same schema as streeteasy-api npm package)."""

SEARCH_RENTALS_QUERY = """
query SearchRentalsFederated($input: SearchRentalsInput!) {
  searchRentals(input: $input) {
    __typename
    edges {
      __typename
      ... on OrganicRentalEdge {
        node {
          __typename
          ...RentalListingDigestForSearchResults
        }
        amenitiesMatch
        matchedAmenities
        missingAmenities
      }
      ... on FeaturedRentalEdge {
        node {
          __typename
          ...RentalListingDigestForSearchResults
        }
        amenitiesMatch
        matchedAmenities
        missingAmenities
      }
      ... on SponsoredRentalEdge {
        node {
          __typename
          ...RentalListingDigestForSearchResults
        }
        sponsoredSimilarityLabel
      }
    }
    totalCount
  }
}
fragment LeadMediaForSRP on LeadMedia {
  __typename
  photo {
    __typename
    key
  }
  floorPlan {
    __typename
    key
  }
}
fragment OpenHouseForSRP on OpenHouseDigest {
  __typename
  startTime
  endTime
  appointmentOnly
}
fragment RentalListingDigestForSearchResults on SearchRentalListing {
  __typename
  id
  areaName
  availableAt
  bedroomCount
  buildingType
  fullBathroomCount
  furnished
  geoPoint {
    __typename
    latitude
    longitude
  }
  halfBathroomCount
  hasTour3d
  hasVideos
  isNewDevelopment
  leadMedia {
    __typename
    ...LeadMediaForSRP
  }
  leaseTermMonths
  livingAreaSize
  mediaAssetCount
  monthsFree
  noFee
  netEffectivePrice
  offMarketAt
  photos {
    __typename
    key
  }
  price
  priceChangedAt
  priceDelta
  slug
  sourceGroupLabel
  sourceType
  status
  street
  unit
  upcomingOpenHouse {
    __typename
    ...OpenHouseForSRP
  }
  urlPath
}
"""

RENTAL_LISTING_DETAILS_QUERY = """
query RentalListingDetailsFederated($listingID: ID!) {
  rentalByListingId(id: $listingID) {
    __typename
    id
    description
    availableAt
    status
    createdAt
    updatedAt
    propertyDetails {
      __typename
      address {
        __typename
        street
        city
        state
        zipCode
        unit
      }
      amenities {
        __typename
        list
      }
    }
    pricing {
      __typename
      price
      noFee
    }
  }
  getRelloRentalById(id: $listingID) {
    __typename
    ctaEnabled
    link
  }
}
"""
