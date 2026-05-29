from urllib import error, response

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout
from django.db.models import Sum, Avg, Q, Count
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator
from django.conf import settings
from django.utils import timezone
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
import json, uuid
from datetime import date, timedelta
from groq import Groq
from .models import (
    Event,
    News,
    Attribute,
    CoreValue,
    NewsEdition,
    Feedback,
    AdminActivity,
    VisitorLog,
    EventCoreValue,
    EventRegistration,
)
from .recommendation import (get_recommended_events, get_latest_news)
from .sentiment import sentiment_analyzer


# =====================
# ADMIN AUTH HELPER
# =====================
def admin_login_required(view_func):
    """Decorator: redirect ke login page kalau belum login sebagai admin."""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('is_admin'):
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# =====================
# ADMIN LOGIN / LOGOUT
# =====================
def admin_login_view(request):
    if request.session.get('is_admin'):
        return redirect('admin_home')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        # Autentikasi pakai Django auth (superuser / staff)
        user = authenticate(request, username=username, password=password)

        if user is not None and (user.is_staff or user.is_superuser):
            login(request, user)
            request.session['is_admin'] = True
            request.session['admin_username'] = user.username
            return redirect('admin_home')
        else:
            error = 'Username atau password salah, atau akun tidak memiliki akses admin.'

    return render(request, 'cms/admin_login.html', {'error': error})


def admin_logout_view(request):
    request.session.flush()
    logout(request)
    return redirect('home')

# =====================
# USER PAGES
# ====================
from django.db.models import Avg
from .models import VisitorLog, Event, News, Attribute, CoreValue

def home(request):
        
    VisitorLog.objects.create(
        page_visited='home',
        visit_duration=10,
        engagement_score=0.8,
    )

    avg_score = VisitorLog.objects.aggregate(
        avg=Avg('engagement_score')
    )['avg'] or 0
    engagement_score = round(float(avg_score) * 100)

    context = {
        "total_events": Event.objects.count(),
        "total_news": News.objects.count(),
        "total_attributes": Attribute.objects.count(),
        "core_values": CoreValue.objects.all(),

        "recommended_events": get_recommended_events(),
        "latest_news": get_latest_news(),

        "engagement_score": engagement_score,
    }

    return render(request, "cms/home.html", context)

def get_recommended_events(core_name=None):
    qs = Event.objects.all()

    if core_name:
        qs = qs.filter(core_values__core_value_name=core_name)

    return qs.distinct()

def _recommended_items_for_core_slug(core_slug):
    """Map slug (integrity, growth-mindset) to events linked in event_core_values."""
    if not core_slug:
        return []

    core_value = CoreValue.objects.filter(
        core_value_name__iexact=core_slug.replace("-", " ")
    ).first()
    if not core_value:
        return []

    event_ids = EventCoreValue.objects.filter(
        core_value=core_value
    ).values_list("event_id", flat=True)

    events = Event.objects.filter(event_id__in=event_ids).order_by("-created_at")[:12]

    return [
        {
            "id": e.event_id,
            "title": e.event_name,
            "summary": (e.description or "")[:120],
            "image_url": e.image_url or "",
            "location": e.location or "",
            "event_date": str(e.event_date) if e.event_date else "",
            "rating": float(e.rating) if e.rating is not None else None,
            "category": core_value.core_value_name,
        }
        for e in events
    ]


def recommended_content(request):
    core_slug = (request.GET.get("core") or "").strip()
    return JsonResponse({"items": _recommended_items_for_core_slug(core_slug)})


def get_or_create_session(request):

    session_id = request.COOKIES.get('feedback_session')

    if not session_id:
        session_id = str(uuid.uuid4())

    return session_id


def explore(request):

    VisitorLog.objects.create(
        page_visited='explore',
        visit_duration=0,
        engagement_score=0.5,
    )

    session_id = get_or_create_session(request)

    events = Event.objects.all().order_by('-event_date')
    for event in events:

        avg_rating = Feedback.objects.filter(
            event=event,
            rating__isnull=False
        ).aggregate(avg=Avg('rating'))['avg']

        if avg_rating:
            event.rating = round(avg_rating, 1)
        else:
            event.rating = None

    rated_events = Feedback.objects.filter(
        session_id=session_id,
        rating__isnull=False
    ).values_list('event_id', flat=True)

    news_editions = NewsEdition.objects.prefetch_related('news').all()

    playbooks = Attribute.objects.filter(attribute_type='playbook')

    posters = Attribute.objects.filter(
        attribute_type='poster'
    )

    assets = Attribute.objects.filter(
        attribute_type='asset'
    )

    logos = Attribute.objects.filter(
        attribute_type='logo'
    )

    videos = Attribute.objects.filter(
        attribute_type='video'
    )

    context = {
        'events': events,
        'news_editions': news_editions,

        'playbooks': playbooks,
        'posters': posters,
        'assets': assets,
        'logos': logos,
        'videos': videos,

        'today': date.today(),

        'rated_events': rated_events,
    }

    response = render(
        request,
        'cms/explore.html',
        context
    )

    response.set_cookie(
        'feedback_session',
        session_id,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite='Lax'
    )
    return response

def feedback(request):
    return render(request, 'cms/feedback.html')
 
 
def get_or_create_session(request):
    session_id = request.COOKIES.get('feedback_session')

    if not session_id:
        session_id = str(uuid.uuid4())

    return session_id


def classify_feedback(message):
    sentiment = 'neutral'
    confidence = 0.95

    return sentiment, confidence


# =========================================================
# CHAT AI
# =========================================================
@require_http_methods(["POST"])
def chat_with_ai(request):

    try:
        data = json.loads(request.body)

        message  = data.get('message', '').strip()
        event_id = data.get('event_id')

        # ================= VALIDASI =================

        if not message:
            return JsonResponse({
                'status': 'error',
                'message': 'Pesan kosong'
            }, status=400)

        # ================= OPTIONAL EVENT =================
        # event boleh kosong
        event = None

        if event_id:
            try:
                event = Event.objects.get(event_id=event_id)

            except Event.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Event tidak valid'
                }, status=404)

        session_id = get_or_create_session(request)

        sentiment, confidence = classify_feedback(message)

        # ================= HISTORY CHAT =================

        previous_feedbacks = Feedback.objects.filter(
            session_id=session_id
        ).exclude(
            ai_response__isnull=True
        ).order_by('-created_at')[:5]

        previous_feedbacks = reversed(previous_feedbacks)

        # ================= PROMPT =================

        messages = [
            {
                "role": "system",
                "content": (

                    "Kamu adalah asisten digital Pegadaian bernama Digi.\n\n"

                    "Kamu HANYA boleh menjawab topik terkait Pegadaian, seperti:\n"
                    "- budaya digital Pegadaian\n"
                    "- layanan Pegadaian\n"
                    "- aplikasi dan teknologi Pegadaian\n"
                    "- event atau seminar Pegadaian\n"
                    "- transformasi digital Pegadaian\n"
                    "- pengalaman pengguna terhadap Pegadaian\n\n"

                    "Jika user bertanya di luar Pegadaian "
                    "(contoh: politik, game, kesehatan, coding umum, hiburan), "
                    "tolak dengan sopan dan arahkan kembali ke topik Pegadaian.\n\n"

                    "Gunakan bahasa yang sama dengan user.\n"
                    "- Indonesia → jawab Indonesia\n"
                    "- English → jawab English\n"
                    "- Campur → jawab natural\n\n"

                    "Aturan:\n"
                    "- Maksimal 2 kalimat\n"
                    "- Jangan terlalu panjang\n"
                    "- Jawaban harus nyambung dengan chat sebelumnya\n"
                    "- Ramah dan profesional\n"
                    "- Jangan mengulang jawaban yang sama\n"
                    "- Gaya modern AI assistant\n"
                    "- Jika user memberi kritik → respon empati\n"
                    "- Jika user memberi pujian → respon positif singkat\n\n"

                    "Di akhir jawaban tambahkan:\n"
                    "IS_FEEDBACK:true\n"
                    "jika user memberi opini, kritik, pengalaman, atau penilaian.\n\n"

                    "IS_FEEDBACK:false\n"
                    "jika user hanya bertanya informasi biasa."
                )
            }
        ]

        # ================= HISTORY =================

        for fb in previous_feedbacks:

            messages.append({
                "role": "user",
                "content": fb.message
            })

            messages.append({
                "role": "assistant",
                "content": fb.ai_response
            })

        # ================= USER MESSAGE =================

        messages.append({
            "role": "user",
            "content": message
        })

        # ================= AI RESPONSE =================

        client = Groq(api_key=settings.GROQ_API_KEY)

        groq_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=80,
            temperature=0.6,
        )

        full_reply = groq_response.choices[0].message.content.strip()

        # ================= FEEDBACK FLAG =================

        is_feedback = False

        if "IS_FEEDBACK:true" in full_reply:
            is_feedback = True

        reply = (
            full_reply
            .replace("IS_FEEDBACK:true", "")
            .replace("IS_FEEDBACK:false", "")
            .strip()
        )

        # ================= SAVE DB =================

        fb = Feedback.objects.create(
            session_id=session_id,
            event=event,
            message=message,
            ai_response=reply,
            sentiment=sentiment,
            rating=None,
            source_platform='web',
        )

        # ================= CEK RATING =================

        show_rating = False

        # rating hanya muncul kalau:
        # 1. feedback
        # 2. ada event
        # 3. event sudah selesai
        if is_feedback and event:

            already_rated = Feedback.objects.filter(
                session_id=session_id,
                event=event,
                rating__isnull=False
            ).exists()

            show_rating = (
                event.event_date < date.today()
                and not already_rated
            )

        # ================= RESPONSE =================

        response = JsonResponse({
            'status': 'success',
            'reply': reply,
            'feedback_id': fb.feedback_id,
            'sentiment': sentiment,
            'confidence': round(confidence * 100),
            'show_rating': show_rating
        })

        response.set_cookie(
            'feedback_session',
            session_id,
            max_age=60*60*24*30,
            httponly=True,
            samesite='Lax'
        )

        return response

    except Exception as e:

        import traceback
        traceback.print_exc()

        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

# =========================================================
# SAVE RATING
# =========================================================

@require_http_methods(["POST"])
def save_feedback(request):

    try:
        data = json.loads(request.body)

        feedback_id = data.get('feedback_id')
        rating      = data.get('rating')

        if not feedback_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Feedback ID tidak ditemukan'
            }, status=400)

        if not rating:
            return JsonResponse({
                'status': 'error',
                'message': 'Rating wajib diisi'
            }, status=400)

        rating = int(rating)

        if rating < 1 or rating > 5:
            return JsonResponse({
                'status': 'error',
                'message': 'Rating harus 1-5'
            }, status=400)

        session_id = get_or_create_session(request)

        fb = Feedback.objects.get(
            feedback_id=feedback_id
        )

        # ================= CEK SESSION =================
        if fb.session_id != session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Session tidak valid'
            }, status=403)

        # ================= CEK SUDAH RATING =================
        if fb.rating is not None:
            return JsonResponse({
                'status': 'error',
                'message': 'Rating sudah pernah diberikan'
            }, status=400)

        # ================= UPDATE RATING =================
        fb.rating = rating
        fb.save()

        # ================= UPDATE AVG EVENT =================
        avg_rating = Feedback.objects.filter(
            event=fb.event,
            rating__isnull=False
        ).aggregate(avg=Avg('rating'))['avg']

        fb.event.rating = round(avg_rating, 1)
        fb.event.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Rating berhasil disimpan',
            'avg_rating': fb.event.rating
        })

    except Feedback.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Feedback tidak ditemukan'
        }, status=404)

    except Exception as e:
        import traceback
        traceback.print_exc()

        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

def culture_performance(request):
    return render(request, 'cms/culture_performance.html')


def business_performance(request):
    return render(request, 'cms/business_performance.html')


def detail(request, id):
    return render(request, 'cms/detail.html')


# =====================
# EVENT
# =====================
def event_detail(request, id):
    event = get_object_or_404(Event, event_id=id)  # ← pakai event_id=

    # Track content view menggunakan VisitorLog existing
    VisitorLog.objects.create(
        page_visited=f'event_detail/{id}',
        visit_duration=0,
        engagement_score=0.5,
        visitor_ip=request.META.get('REMOTE_ADDR', ''),
    )

    context = {'event': event}
    return render(request, 'cms/event_detail.html', context)

def _format_event_date(event):
    if not event.event_date:
        return "-"
    months = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ]
    d = event.event_date
    return f"{d.day} {months[d.month - 1]} {d.year}"


def register_event(request, id):
    event = get_object_or_404(Event, event_id=id)

    if request.method == "POST":
        nama = (request.POST.get("nama") or "").strip()
        email = (request.POST.get("email") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        instansi = (request.POST.get("instansi") or "").strip()

        errors = []
        if not nama:
            errors.append("Nama lengkap wajib diisi.")
        if not email:
            errors.append("Email wajib diisi.")
        if not phone:
            errors.append("Nomor HP wajib diisi.")

        if errors:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"status": "error", "errors": errors}, status=400)
            return render(
                request,
                "cms/register_form.html",
                {"event": event, "errors": errors, "form": request.POST},
            )

        EventRegistration.objects.create(
            event_name=event.event_name,
            full_name=nama,
            email=email,
            phone=phone,
            organization=instansi or None,
        )

        payload = {
            "status": "success",
            "event_name": event.event_name,
            "event_date": _format_event_date(event),
        }
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(payload)
        return render(
            request,
            "cms/register_form.html",
            {"event": event, "show_success": True, **payload},
        )

    return render(request, "cms/register_form.html", {"event": event})


def success_page(request):
    event_name = request.session.pop("last_registration_event", None)
    return render(request, "cms/success.html", {"event_name": event_name})


# =====================
# API
# =====================

def recommended_content_api(request):
    core_slug = (request.GET.get("core") or "").strip()
    return JsonResponse({"items": _recommended_items_for_core_slug(core_slug)})


@csrf_exempt
def track_activity(request):
    if request.method == "POST":
        data = json.loads(request.body)
        print("Activity:", data)
        return JsonResponse({"status": "tracked"})

    return JsonResponse({"status": "invalid"})


# =====================
# ADMIN PAGES (CUSTOM)
# =====================

def log_admin_activity(message):
    AdminActivity.objects.create(activity=message)


@admin_login_required
def admin_home(request):
    today = timezone.localdate()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.GET.get('action') == 'get_chart_data':
        def format_avg_time(avg_sec):
            if not avg_sec:
                return "0s"
            m = int(avg_sec // 60)
            s = int(avg_sec % 60)
            if m > 0:
                return f"{m}m {s}s"
            return f"{s}s"

        period = request.GET.get('period', '1week')
        labels = []
        data = []
        avg_times = []
        date_range_text = ""
        
        if period == '1week':
            start_date = today - timedelta(days=6)
            date_range_text = f"{start_date.strftime('%b %d %Y')} - {today.strftime('%b %d %Y')}"
            days = [start_date + timedelta(days=i) for i in range(7)]
            labels = [d.strftime('%d/%m') for d in days]
            
            qs = VisitorLog.objects.filter(visited_at__date__gte=start_date, visited_at__date__lte=today)
            agg = qs.annotate(period_val=TruncDay('visited_at')).values('period_val').annotate(
                count=Count('log_id'),
                avg_duration=Avg('visit_duration')
            )
            
            count_map = {}
            avg_map = {}
            for item in agg:
                if item['period_val']:
                    dt = timezone.localtime(item['period_val']).date() if timezone.is_aware(item['period_val']) else item['period_val'].date()
                    count_map[dt] = count_map.get(dt, 0) + item['count']
                    # We'll take the average directly if they match exact days, but for simple visualization, taking the first or max is fine,
                    # or better yet, since it groups by day, we just take item['avg_duration']
                    avg_map[dt] = item['avg_duration']
                    
            for d in days:
                data.append(count_map.get(d, 0))
                avg_times.append(format_avg_time(avg_map.get(d, 0)))
            
        elif period == '1month':
            start_date = today - timedelta(days=29)
            date_range_text = f"{start_date.strftime('%b %d %Y')} - {today.strftime('%b %d %Y')}"
            days = [start_date + timedelta(days=i) for i in range(30)]
            labels = [d.strftime('%d/%m') for d in days]
            
            qs = VisitorLog.objects.filter(visited_at__date__gte=start_date, visited_at__date__lte=today)
            agg = qs.annotate(period_val=TruncDay('visited_at')).values('period_val').annotate(
                count=Count('log_id'),
                avg_duration=Avg('visit_duration')
            )
            
            count_map = {}
            avg_map = {}
            for item in agg:
                if item['period_val']:
                    dt = timezone.localtime(item['period_val']).date() if timezone.is_aware(item['period_val']) else item['period_val'].date()
                    count_map[dt] = count_map.get(dt, 0) + item['count']
                    avg_map[dt] = item['avg_duration']
                    
            for d in days:
                data.append(count_map.get(d, 0))
                avg_times.append(format_avg_time(avg_map.get(d, 0)))
            
        elif period in ['6months', '1year']:
            months_count = 6 if period == '6months' else 12
            start_date = today.replace(day=1)
            for _ in range(months_count - 1):
                start_date = (start_date - timedelta(days=1)).replace(day=1)
                
            date_range_text = f"{start_date.strftime('%b %Y')} - {today.strftime('%b %Y')}"
            
            months_list = []
            curr = start_date
            for _ in range(months_count):
                months_list.append((curr.year, curr.month))
                curr = (curr.replace(day=28) + timedelta(days=4)).replace(day=1)
                
            labels = [date(m[0], m[1], 1).strftime('%b') for m in months_list]
            
            qs = VisitorLog.objects.filter(visited_at__date__gte=start_date, visited_at__date__lte=today)
            agg = qs.annotate(period_val=TruncMonth('visited_at')).values('period_val').annotate(
                count=Count('log_id'),
                avg_duration=Avg('visit_duration')
            )
            
            count_map = {}
            avg_map = {}
            for item in agg:
                if item['period_val']:
                    dt = timezone.localtime(item['period_val']).date() if timezone.is_aware(item['period_val']) else item['period_val'].date()
                    count_map[(dt.year, dt.month)] = count_map.get((dt.year, dt.month), 0) + item['count']
                    avg_map[(dt.year, dt.month)] = item['avg_duration']
                    
            for m in months_list:
                data.append(count_map.get(m, 0))
                avg_times.append(format_avg_time(avg_map.get(m, 0)))
            
        return JsonResponse({
            'labels': labels,
            'data': data,
            'avg_times': avg_times,
            'date_range_text': date_range_text
        })

    # Default initial data for 1week
    start_date_initial = today - timedelta(days=6)
    initial_date_range_text = f"{start_date_initial.strftime('%b %d %Y')} - {today.strftime('%b %d %Y')}"
    days = [start_date_initial + timedelta(days=i) for i in range(7)]
    weekly_labels = [d.strftime('%d/%m') for d in days]
    
    def format_avg_time(avg_sec):
        if not avg_sec:
            return "0s"
        m = int(avg_sec // 60)
        s = int(avg_sec % 60)
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"
        
    qs_initial = VisitorLog.objects.filter(visited_at__date__gte=start_date_initial, visited_at__date__lte=today)
    agg_initial = qs_initial.annotate(period_val=TruncDay('visited_at')).values('period_val').annotate(
        count=Count('log_id'),
        avg_duration=Avg('visit_duration')
    )
    
    count_map_initial = {}
    avg_map_initial = {}
    for item in agg_initial:
        if item['period_val']:
            dt = timezone.localtime(item['period_val']).date() if timezone.is_aware(item['period_val']) else item['period_val'].date()
            count_map_initial[dt] = count_map_initial.get(dt, 0) + item['count']
            avg_map_initial[dt] = item['avg_duration']
            
    weekly_data = []
    weekly_avg_times = []
    for d in days:
        weekly_data.append(count_map_initial.get(d, 0))
        weekly_avg_times.append(format_avg_time(avg_map_initial.get(d, 0)))

    total_visits = VisitorLog.objects.count()
    avg_visit_seconds = VisitorLog.objects.aggregate(avg_duration=Avg('visit_duration'))['avg_duration'] or 0
    avg_time = f"{int(avg_visit_seconds // 60)}m {int(avg_visit_seconds % 60)}s"
    avg_engagement_score = VisitorLog.objects.aggregate(avg_engagement=Avg('engagement_score'))['avg_engagement'] or 0
    if avg_engagement_score >= 0.7:
        engagement_text = 'High'
    elif avg_engagement_score >= 0.4:
        engagement_text = 'Medium'
    else:
        engagement_text = 'Low'

    last_week_visits = VisitorLog.objects.filter(visited_at__date__gte=start_date_initial, visited_at__date__lte=today).count()
    previous_week_visits = VisitorLog.objects.filter(visited_at__date__gte=start_date_initial - timedelta(days=7), visited_at__date__lt=start_date_initial).count()
    if previous_week_visits:
        trends = f"{round((last_week_visits - previous_week_visits) / previous_week_visits * 100)}%"
    else:
        trends = f"+{last_week_visits * 10}%" if last_week_visits else "0%"

    total_content = Event.objects.count() + News.objects.count() + Attribute.objects.count()
    total_views = VisitorLog.objects.count()
    active_content = Event.objects.filter(event_date__gte=today).count()
    total_feedback = Feedback.objects.count()

    feedback_messages = [item.message for item in Feedback.objects.all()]
    common_words = sentiment_analyzer.extract_common_words(feedback_messages, limit=6)
    common_word_list = [{'word': word, 'count': count} for word, count in common_words]

    event_keywords = {
        'Culture Workshop 2026': ['culture', 'workshop', '2026'],
        'Team Building Day': ['team building', 'team', 'building'],
        'Leadership Seminar': ['leadership', 'seminar'],
    }
    event_ranking = []
    for event_name, keywords in event_keywords.items():
        query = None
        for keyword in keywords:
            q = Q(message__icontains=keyword)
            query = q if query is None else query | q

        if query is None:
            continue

        event_feedback = Feedback.objects.filter(query)
        total_event = event_feedback.count()
        positive_event = event_feedback.filter(sentiment='positive').count()
        negative_event = event_feedback.filter(sentiment='negative').count()
        if total_event:
            event_ranking.append({
                'event': event_name,
                'total': total_event,
                'positive': positive_event,
                'negative': negative_event,
                'score': round(positive_event / total_event * 100),
            })

    event_ranking.sort(key=lambda row: row['score'], reverse=True)
    event_ranking = event_ranking[:5]

    total_positive = Feedback.objects.filter(sentiment='positive').count()
    total_neutral = Feedback.objects.filter(sentiment='neutral').count()
    total_negative = Feedback.objects.filter(sentiment='negative').count()

    if total_feedback:
        positive_percent = round(total_positive / total_feedback * 100)
        neutral_percent = round(total_neutral / total_feedback * 100)
        negative_percent = round(total_negative / total_feedback * 100)
    else:
        positive_percent = neutral_percent = negative_percent = 0

    recent_admin_activities = list(AdminActivity.objects.all().order_by('-created_at')[:6])
    recent_feedbacks = list(Feedback.objects.order_by('-created_at')[:10])

    def format_activity_time(dt):
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        now = timezone.localtime(timezone.now())
        dt = timezone.localtime(dt)
        diff = now - dt
        seconds = diff.seconds
        if diff.days == 0:
            if seconds < 60:
                return f"{seconds}s ago"
            if seconds < 3600:
                return f"{seconds // 60}m ago"
            return f"Today {dt.strftime('%H:%M')}"
        if diff.days == 1:
            return f"Yesterday {dt.strftime('%H:%M')}"
        if diff.days < 7:
            return f"{diff.days} days ago"
        return dt.strftime('%d %b %Y %H:%M')

    recent_admin_activities_data = []
    for activity in reversed(recent_admin_activities):
        recent_admin_activities_data.append({
            'icon': '📝',
            'title': activity.activity,
            'when': format_activity_time(activity.created_at),
        })

    recent_feedbacks_data = []
    for fb in recent_feedbacks:
        preview = fb.message.strip().replace('\n', ' ')
        if len(preview) > 90:
            preview = preview[:90].rsplit(' ', 1)[0] + '...'
        recent_feedbacks_data.append({
            'comment': preview,
            'sentiment': fb.sentiment.capitalize(),
            'rating': fb.rating if fb.rating is not None else 'N/A',
            'platform': fb.source_platform.capitalize(),
            'when': format_activity_time(fb.created_at),
        })

    context = {
        'total_content': total_content,
        'total_views': total_views,
        'active_content': active_content,
        'total_feedback': total_feedback,
        'weekly_data': weekly_data,
        'weekly_avg_times_json': json.dumps(weekly_avg_times),
        'weekly_labels': weekly_labels,
        'weekly_data_json': json.dumps(weekly_data),
        'weekly_labels_json': json.dumps(weekly_labels),
        'initial_date_range_text': initial_date_range_text,
        'recent_admin_activities': recent_admin_activities_data,
        'recent_feedbacks': recent_feedbacks_data,
        'total_visits': total_visits,
        'avg_time': avg_time,
        'engagement_text': engagement_text,
        'trends': trends,
        'positive': total_positive,
        'neutral': total_neutral,
        'negative': total_negative,
        'positive_percent': positive_percent,
        'neutral_percent': neutral_percent,
        'negative_percent': negative_percent,
        'event_ranking': event_ranking,
    }
    return render(request, 'cms/admin.html', context)


@admin_login_required
def explore_admin(request):
    events = Event.objects.all().order_by('-event_date')
    today = date.today()

    for event in events:
        if event.event_date:
            event.status = 'Active' if event.event_date >= today else 'Inactive'
        else:
            event.status = 'Unknown'
        event.views = VisitorLog.objects.filter(
            page_visited=f'event_detail/{event.event_id}'
        ).count()

    return render(request, 'cms/explore_admin.html', {'events': events})


@admin_login_required
def admin_add_event(request):
    if request.method == 'POST':
        event_name = request.POST.get('event_name', '').strip()
        description = request.POST.get('description', '').strip()
        location = request.POST.get('location', '').strip()
        event_date = request.POST.get('event_date')
        event_time = request.POST.get('event_time')

        image_file = request.FILES.get('image')  # ← ambil file, TANPA strip()

        image_path = None
        if image_file:
            fs = FileSystemStorage(location='media/events')
            filename = fs.save(image_file.name, image_file)
            image_path = f'events/{filename}'  # ← ini yang disimpan ke DB

        if event_name:
            Event.objects.create(
                event_name=event_name,
                description=description or None,
                location=location or None,
                event_date=date.fromisoformat(event_date) if event_date else None,
                event_time=event_time or None,
                image_url=image_path  # ← simpan path text
            )
            log_admin_activity(f"Event '{event_name}' dibuat")
            return redirect('admin_explore')

    return render(request, 'cms/event_form.html', {
        'action': 'Tambah Event',
        'event': None,
        'form_action': 'admin_add_event',
    })

@admin_login_required
def admin_edit_event(request, id):
    event = get_object_or_404(Event, event_id=id)
    if request.method == 'POST':
        old_name = event.event_name
        event.event_name = request.POST.get('event_name', '').strip() or event.event_name
        event.description = request.POST.get('description', '').strip() or event.description
        event.location = request.POST.get('location', '').strip() or event.location
        event_date = request.POST.get('event_date')
        event_time = request.POST.get('event_time')

        image_file = request.FILES.get('image')
        if image_file:
            fs = FileSystemStorage(location='media/events')
            filename = fs.save(image_file.name, image_file)
            event.image_url = f'events/{filename}'

        event.event_date = date.fromisoformat(event_date) if event_date else event.event_date
        event.event_time = event_time or event.event_time
        event.save()
        log_admin_activity(f"Event '{old_name}' diperbarui menjadi '{event.event_name}'")
        return redirect('admin_explore')

    return render(request, 'cms/event_form.html', {
        'action': 'Edit Event',
        'event': event,
        'form_action': 'admin_edit_event',
    })


@admin_login_required
def admin_delete_event(request, id):
    if request.method == 'POST':
        event = get_object_or_404(Event, event_id=id)
        event_name = event.event_name
        event.delete()
        log_admin_activity(f"Event '{event_name}' dihapus")
    return redirect('admin_explore')


@admin_login_required
def feedback_admin(request):
    selected_event = request.GET.get('event', 'all')
    selected_sentiment = request.GET.get('sentiment', 'all')
    page_number = request.GET.get('page', 1)

    event_options = list(Event.objects.order_by('event_name').values_list('event_name', flat=True))

    def build_event_query(event_name):
        tokens = [token.strip() for token in event_name.lower().split() if len(token.strip()) > 2]
        query = None
        for token in tokens:
            q = Q(message__icontains=token)
            query = q if query is None else query | q
        return query

    def detect_event(message):
        text = message.lower()
        for event_name in event_options:
            if not event_name:
                continue
            lower_name = event_name.lower()
            if lower_name in text:
                return event_name
            for token in lower_name.split():
                if len(token) > 2 and token in text:
                    return event_name
        return 'General'

    feedback_qs = Feedback.objects.order_by('-created_at')

    if selected_sentiment != 'all':
        feedback_qs = feedback_qs.filter(sentiment=selected_sentiment)

    if selected_event != 'all' and selected_event in event_options:
        query = build_event_query(selected_event)
        if query is not None:
            feedback_qs = feedback_qs.filter(query)

    total_positive = Feedback.objects.filter(sentiment='positive').count()
    total_neutral = Feedback.objects.filter(sentiment='neutral').count()
    total_negative = Feedback.objects.filter(sentiment='negative').count()
    total_feedback = total_positive + total_neutral + total_negative

    if total_feedback:
        positive_percent = round(total_positive / total_feedback * 100)
        neutral_percent = round(total_neutral / total_feedback * 100)
        negative_percent = round(total_negative / total_feedback * 100)
    else:
        positive_percent = neutral_percent = negative_percent = 0

    feedback_entries = []
    for fb in feedback_qs:
        sentiment_label = fb.sentiment.capitalize()
        sentiment_text = f"{sentiment_label}"
        confidence = None
        try:
            _, confidence = sentiment_analyzer.predict(fb.message)
            sentiment_text = f"{sentiment_label} ({round(confidence * 100)}%)"
        except Exception:
            confidence = None

        feedback_entries.append({
            'comment': fb.message,
            'time': fb.created_at.strftime('%d %b %Y %H:%M'),
            'user': fb.session_id or 'Anonymous',
            'event': detect_event(fb.message),
            'sentiment': sentiment_text,
            'rating': fb.rating if fb.rating is not None else 'N/A',
            'platform': fb.source_platform.capitalize(),
            'confidence': confidence,
        })

    paginator = Paginator(feedback_entries, 10)
    page_obj = paginator.get_page(page_number)

    most_common = sentiment_analyzer.extract_common_words(
        [fb.message for fb in Feedback.objects.all()], limit=8
    )
    most_common_words = [{'word': word, 'count': count} for word, count in most_common]

    context = {
        'feedbacks': page_obj,
        'page_obj': page_obj,
        'selected_event': selected_event,
        'selected_sentiment': selected_sentiment,
        'positive': total_positive,
        'neutral': total_neutral,
        'negative': total_negative,
        'positive_percent': positive_percent,
        'neutral_percent': neutral_percent,
        'negative_percent': negative_percent,
        'event_options': event_options,
        'most_common_words': most_common_words,
    }

    return render(request, 'cms/feedback_admin.html', context)


# ADMIN LOGIN
def admin_login(request):
    if request.session.get('is_admin'):
        return redirect('admin_home')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        if username == 'Admin' and password == '1234':
            request.session['is_admin'] = True
            return redirect('admin_home')
        else:
            error = 'Username atau password salah.'
    return render(request, 'cms/admin_login.html', {'error': error})


def admin_logout(request):
    request.session.flush()
    return redirect('admin_login')

def admin_login(request):
    if request.session.get('is_admin'):
        from django.shortcuts import redirect
        return redirect('admin_home')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        if username == 'Admin' and password == '1234':
            request.session['is_admin'] = True
            request.session.save()
            from django.shortcuts import redirect
            return redirect('admin_home')
        else:
            error = 'Username atau password salah.'
    from django.shortcuts import render
    return render(request, 'cms/admin_login.html', {'error': error})

def admin_logout(request):
    request.session.flush()
    from django.shortcuts import redirect
    return redirect('admin_login')

def admin_login(request):
    if request.session.get('is_admin'):
        from django.shortcuts import redirect
        return redirect('admin_home')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        if username == 'Admin' and password == '1234':
            request.session['is_admin'] = True
            request.session.save()
            from django.shortcuts import redirect
            return redirect('admin_home')
        else:
            error = 'Username atau password salah.'
    from django.shortcuts import render
    return render(request, 'cms/admin_login.html', {'error': error})

def admin_logout(request):
    request.session.flush()
    from django.shortcuts import redirect
    return redirect('admin_login')
