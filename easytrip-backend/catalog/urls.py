from rest_framework.routers import DefaultRouter
from .views import (
    CountryViewSet, CityViewSet, AirportViewSet, ActivityCategoryViewSet,
    HotelViewSet, ActivityViewSet, FlightViewSet,
)

router = DefaultRouter()
router.register('countries', CountryViewSet, basename='country')
router.register('cities', CityViewSet, basename='city')
router.register('airports', AirportViewSet, basename='airport')
router.register('activity-categories', ActivityCategoryViewSet, basename='activity-category')
router.register('hotels', HotelViewSet, basename='hotel')
router.register('activities', ActivityViewSet, basename='activity')
router.register('flights', FlightViewSet, basename='flight')

urlpatterns = router.urls
