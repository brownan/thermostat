from django.shortcuts import render


async def home(request):
    return render(request, "home.html")
