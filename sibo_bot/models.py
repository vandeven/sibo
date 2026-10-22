from typing import Self

from pydantic import BaseModel, Field, model_validator


class Dish(BaseModel):
    name: str
    price: str = Field(
        description="Menu price in euros, e.g. '€14.50'. Prices in another currency are converted at the current "
        "exchange rate and marked approximate, e.g. '~€12'. 'unknown' if not found."
    )
    why_sibo_friendly: str = Field(description="Why this dish is (or becomes) low-FODMAP / low-fermentation.")
    modifications: list[str] = Field(
        description="Concrete changes to request from the waiter to make the dish SIBO-friendly. "
        "Empty if the dish is safe as served."
    )


class Restaurant(BaseModel):
    name: str
    address: str
    rating: str = Field(description="Average review rating with source scale, e.g. '4.6/5'.")
    price_level: str = Field(
        description="Price level in words plus typical main-course price in euros, e.g. 'moderate (mains €15-22)'."
    )
    distance_km: float | None = Field(
        default=None, description="Distance from the user's coordinates in km. Only for location searches."
    )
    dishes: list[Dish]


class RestaurantReport(BaseModel):
    location_label: str = Field(description="Human-readable search area, e.g. 'Wageningen' or 'Utrecht, Lombok'.")
    cuisine: str | None = None
    top_rated: list[Restaurant] = Field(description="Up to 5 best-rated restaurants, best first.")
    cheapest: list[Restaurant] = Field(description="Up to 5 cheapest restaurants, cheapest first.")
    notes: str | None = Field(default=None, description="Caveats, e.g. a widened search radius.")


class SearchQuery(BaseModel):
    city: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    cuisine: str | None = None

    @model_validator(mode="after")
    def _require_city_or_coordinates(self) -> Self:
        has_coords = self.latitude is not None and self.longitude is not None
        if not self.city and not has_coords:
            raise ValueError("A search needs either a city or both latitude and longitude.")
        return self

    @property
    def is_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def label(self) -> str:
        if self.is_location:
            return f"your location ({self.latitude:.4f}, {self.longitude:.4f})"
        return self.city or ""

    @classmethod
    def from_text(cls, text: str) -> "SearchQuery":
        """'Wageningen Italian' -> city='Wageningen', cuisine='Italian'."""
        city, _, cuisine = text.strip().partition(" ")
        return cls(city=city, cuisine=cuisine.strip() or None)
