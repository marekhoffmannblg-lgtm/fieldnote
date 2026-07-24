export interface PreviewOfferSelection {
  selectable: boolean;
}

export function canSelectPreviewOffer(allowSelection: boolean, offer: PreviewOfferSelection) {
  return allowSelection && offer.selectable;
}
