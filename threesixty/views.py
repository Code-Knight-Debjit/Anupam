from django.shortcuts import render

from .permissions import staff_360_required


@staff_360_required
def index(request):
    """Placeholder landing page — the full Kinetic-Architect SPA shell lands
    in Phase 3/4. For now this just proves the auth chain (staff + has an
    EmployeeProfile) works end to end."""
    return render(request, 'threesixty/index.html', {
        'profile': request.user.threesixty_profile,
    })
