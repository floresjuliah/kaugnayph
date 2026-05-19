# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Announcementcategories(models.Model):
    acid = models.AutoField(db_column='ACid', primary_key=True)  # Field name made lowercase.
    name = models.CharField(unique=True, max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'AnnouncementCategories'


class Announcementfeedback(models.Model):
    afid = models.AutoField(db_column='AFID', primary_key=True)  # Field name made lowercase.
    rating = models.IntegerField()
    created_at = models.DateTimeField(blank=True, null=True)
    announcement = models.ForeignKey('Announcements', models.DO_NOTHING)
    user = models.ForeignKey('Users', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'AnnouncementFeedback'
        unique_together = (('announcement', 'user'),)


class Announcements(models.Model):
    announcement_id = models.AutoField(db_column='Announcement_id', primary_key=True)  # Field name made lowercase.
    title = models.CharField(max_length=255, blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    file = models.TextField(db_column='File', blank=True, null=True)  # Field name made lowercase.
    file_path = models.CharField(max_length=255, blank=True, null=True)
    send_sms = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    category = models.ForeignKey(Announcementcategories, models.DO_NOTHING, blank=True, null=True)
    posted_by = models.ForeignKey('Users', models.DO_NOTHING, db_column='posted_by', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Announcements'


class Auditlogs(models.Model):
    logid = models.AutoField(db_column='LogID', primary_key=True)  # Field name made lowercase.
    action = models.CharField(max_length=100)
    module_name = models.CharField(max_length=50, blank=True, null=True)
    table_name = models.CharField(max_length=100, blank=True, null=True)
    record_id = models.IntegerField(blank=True, null=True)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    ip_address = models.CharField(max_length=50, blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    user = models.ForeignKey('Users', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'AuditLogs'


class Complainthearing(models.Model):
    chid = models.AutoField(db_column='CHID', primary_key=True)  # Field name made lowercase.
    hearing_date = models.DateTimeField()
    created_at = models.DateTimeField(blank=True, null=True)
    complaint = models.ForeignKey('Complaints', models.DO_NOTHING)
    hearing_level = models.ForeignKey('Hearinglevel', models.DO_NOTHING)
    status = models.ForeignKey('Hearingstatus', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'ComplaintHearing'


class Complainttype(models.Model):
    ctid = models.AutoField(db_column='CTID', primary_key=True)  # Field name made lowercase.
    type = models.CharField(db_column='Type', max_length=100, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'ComplaintType'


class Complaintupdates(models.Model):
    cuid = models.AutoField(db_column='CUID', primary_key=True)  # Field name made lowercase.
    status = models.CharField(max_length=50, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    complaint = models.ForeignKey('Complaints', models.DO_NOTHING, blank=True, null=True)
    updated_by = models.ForeignKey('Users', models.DO_NOTHING, db_column='updated_by', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ComplaintUpdates'


class Complaints(models.Model):
    complaintsid = models.AutoField(db_column='ComplaintsID', primary_key=True)  # Field name made lowercase.
    complainee = models.CharField(max_length=255, blank=True, null=True)
    title = models.CharField(db_column='Title', max_length=255, blank=True, null=True)  # Field name made lowercase.
    description = models.TextField(db_column='Description', blank=True, null=True)  # Field name made lowercase.
    file = models.TextField(db_column='File', blank=True, null=True)  # Field name made lowercase.
    file_path = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=12, blank=True, null=True)
    dateadded = models.DateTimeField(db_column='DateAdded')  # Field name made lowercase.
    datefinish = models.DateTimeField(db_column='DateFinish', blank=True, null=True)  # Field name made lowercase.
    complaint_type = models.ForeignKey(Complainttype, models.DO_NOTHING, blank=True, null=True)
    complainant_user = models.ForeignKey('Users', models.DO_NOTHING, blank=True, null=True)
    handled_by = models.ForeignKey('Users', models.DO_NOTHING, db_column='handled_by', related_name='complaints_handled_by_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Complaints'


class Documentfields(models.Model):
    dfid = models.AutoField(db_column='DFID', primary_key=True)  # Field name made lowercase.
    field_label = models.CharField(max_length=100, blank=True, null=True)
    field_type = models.CharField(max_length=20, blank=True, null=True)
    is_required = models.IntegerField(blank=True, null=True)
    document_type = models.ForeignKey('Documenttypes', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'DocumentFields'


class Documentrequestfieldvalues(models.Model):
    drfvid = models.AutoField(db_column='DRFVID', primary_key=True)  # Field name made lowercase.
    document_request = models.ForeignKey('Documentrequests', models.DO_NOTHING)
    document_field = models.ForeignKey(Documentfields, models.DO_NOTHING)
    field_value = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'DocumentRequestFieldValues'


class Documentrequests(models.Model):
    drid = models.AutoField(db_column='DRID', primary_key=True)  # Field name made lowercase.
    request_mode = models.CharField(max_length=20, blank=True, null=True)
    purpose = models.TextField(blank=True, null=True)
    generated_file = models.CharField(max_length=255, blank=True, null=True)
    uploaded_file = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=10, blank=True, null=True)
    requested_at = models.DateTimeField()
    processed_at = models.DateTimeField(blank=True, null=True)
    document_type = models.ForeignKey('Documenttypes', models.DO_NOTHING, blank=True, null=True)
    processed_by = models.ForeignKey('Users', models.DO_NOTHING, db_column='processed_by', blank=True, null=True)
    user = models.ForeignKey('Users', models.DO_NOTHING, related_name='documentrequests_user_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'DocumentRequests'


class Documenttypes(models.Model):
    dtid = models.AutoField(db_column='DTID', primary_key=True)  # Field name made lowercase.
    name = models.CharField(unique=True, max_length=100, blank=True, null=True)
    is_active = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'DocumentTypes'


class Hearinglevel(models.Model):
    hearinglevelid = models.AutoField(db_column='HearingLevelID', primary_key=True)  # Field name made lowercase.
    level_type = models.CharField(db_column='Level_Type', max_length=100, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'HearingLevel'


class Hearingofficials(models.Model):
    hoid = models.AutoField(db_column='HOID', primary_key=True)  # Field name made lowercase.
    role = models.CharField(max_length=50, blank=True, null=True)
    complaint = models.ForeignKey(Complaints, models.DO_NOTHING)
    user_officials = models.ForeignKey('Users', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'HearingOfficials'


class Hearingstatus(models.Model):
    statusid = models.AutoField(db_column='StatusID', primary_key=True)  # Field name made lowercase.
    statustype = models.CharField(db_column='StatusType', max_length=100, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'HearingStatus'


class Inquiry(models.Model):
    cuid = models.AutoField(db_column='CUID', primary_key=True)  # Field name made lowercase.
    firstname = models.CharField(db_column='Firstname', max_length=250)  # Field name made lowercase.
    lastname = models.CharField(db_column='Lastname', max_length=250)  # Field name made lowercase.
    contactno = models.CharField(db_column='ContactNo', max_length=20)  # Field name made lowercase.
    address = models.CharField(db_column='Address', max_length=100, blank=True, null=True)  # Field name made lowercase.
    messagesubject = models.CharField(db_column='MessageSubject', max_length=255, blank=True, null=True)  # Field name made lowercase.
    message = models.TextField(db_column='Message', blank=True, null=True)  # Field name made lowercase.
    status = models.CharField(db_column='Status', max_length=7, blank=True, null=True)  # Field name made lowercase.
    admin_reply = models.TextField(blank=True, null=True)
    replied_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    replied_byuser = models.ForeignKey('Users', models.DO_NOTHING, db_column='replied_byUser', blank=True, null=True)  # Field name made lowercase.
    user = models.ForeignKey('Users', models.DO_NOTHING, related_name='inquiry_user_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Inquiry'


class Otp(models.Model):
    otpid = models.AutoField(db_column='OtpID', primary_key=True)  # Field name made lowercase.
    code = models.CharField(db_column='Code', max_length=10, blank=True, null=True)  # Field name made lowercase.
    purpose = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(db_column='Created_at')  # Field name made lowercase.
    expires_at = models.DateTimeField(blank=True, null=True)
    is_used = models.IntegerField()
    user = models.ForeignKey('Users', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'OTP'


class Permissions(models.Model):
    permissionid = models.AutoField(db_column='PermissionID', primary_key=True)  # Field name made lowercase.
    name = models.CharField(unique=True, max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Permissions'


class Positions(models.Model):
    positionid = models.AutoField(db_column='PositionID', primary_key=True)  # Field name made lowercase.
    name = models.CharField(db_column='Name', unique=True, max_length=100, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'Positions'


class Residentverification(models.Model):
    rv_id = models.AutoField(db_column='RV_ID', primary_key=True)  # Field name made lowercase.
    id_image = models.TextField(blank=True, null=True)
    id_image_path = models.CharField(max_length=255, blank=True, null=True)
    selfie_image = models.TextField(blank=True, null=True)
    selfie_image_path = models.CharField(max_length=255, blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=8, blank=True, null=True)
    toid = models.ForeignKey('Typeofid', models.DO_NOTHING, db_column='ToID', blank=True, null=True)  # Field name made lowercase.
    reviewed_by = models.ForeignKey('Users', models.DO_NOTHING, db_column='reviewed_by', blank=True, null=True)
    user = models.ForeignKey('Users', models.DO_NOTHING, related_name='residentverification_user_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ResidentVerification'


class Rolepermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    permissionid = models.ForeignKey(Permissions, models.DO_NOTHING, db_column='PermissionID')  # Field name made lowercase.
    roleid = models.ForeignKey('Roles', models.DO_NOTHING, db_column='RoleID')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'RolePermissions'
        unique_together = (('roleid', 'permissionid'),)


class Roles(models.Model):
    roleid = models.AutoField(db_column='RoleID', primary_key=True)  # Field name made lowercase.
    rolename = models.CharField(db_column='RoleName', unique=True, max_length=50, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'Roles'


class Slamodules(models.Model):
    moduleid = models.AutoField(db_column='ModuleID', primary_key=True)  # Field name made lowercase.
    module_name = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'SLAModules'


class Slatracking(models.Model):
    slaid = models.AutoField(db_column='SLAID', primary_key=True)  # Field name made lowercase.
    record_id = models.IntegerField(blank=True, null=True)
    priority_level = models.CharField(max_length=6, blank=True, null=True)
    sla_deadline = models.DateTimeField(blank=True, null=True)
    first_response_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    sla_status = models.CharField(max_length=11, blank=True, null=True)
    response_time_minutes = models.IntegerField(blank=True, null=True)
    resolution_time_minutes = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    module = models.ForeignKey(Slamodules, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'SLATracking'


class Smsmodules(models.Model):
    smsmoduleid = models.AutoField(db_column='SMSModuleID', primary_key=True)  # Field name made lowercase.
    module_name = models.CharField(unique=True, max_length=50)

    class Meta:
        managed = False
        db_table = 'SMSModules'


class Smssubscriptions(models.Model):
    is_active = models.IntegerField(blank=True, null=True)
    user = models.OneToOneField('Users', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'SMSSubscriptions'


class SmsOutbox(models.Model):
    outboxid = models.AutoField(db_column='OutboxID', primary_key=True)  # Field name made lowercase.
    recipient_number = models.CharField(max_length=20, blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    module = models.ForeignKey(Smsmodules, models.DO_NOTHING, blank=True, null=True)
    related_record_id = models.IntegerField(blank=True, null=True)
    user = models.ForeignKey('Users', models.DO_NOTHING, blank=True, null=True)
    status = models.CharField(max_length=7, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    gateway_response = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    sent_by = models.ForeignKey('Users', models.DO_NOTHING, db_column='sent_by', related_name='smsoutbox_sent_by_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'SMS_Outbox'


class Settings(models.Model):
    settingsid = models.AutoField(db_column='SettingsID', primary_key=True)  # Field name made lowercase.
    notifications_enabled = models.IntegerField(blank=True, null=True)
    dark_mode = models.IntegerField(blank=True, null=True)
    text_size = models.CharField(max_length=10, blank=True, null=True)
    receive_sms = models.IntegerField(db_column='receive_SMS', blank=True, null=True)  # Field name made lowercase.
    updated_at = models.DateTimeField(blank=True, null=True)
    user = models.ForeignKey('Users', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Settings'


class Typeofid(models.Model):
    toid = models.AutoField(db_column='ToID', primary_key=True)  # Field name made lowercase.
    name = models.CharField(db_column='Name', max_length=100, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'TypeOfID'


class Usertypes(models.Model):
    usertypeid = models.AutoField(db_column='UserTypeID', primary_key=True)  # Field name made lowercase.
    type_name = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'UserTypes'


class Users(models.Model):
    userid = models.AutoField(db_column='UserID', primary_key=True)  # Field name made lowercase.
    username = models.CharField(db_column='Username', unique=True, max_length=50)  # Field name made lowercase.
    password = models.CharField(db_column='Password', max_length=255)  # Field name made lowercase.
    firstname = models.CharField(db_column='Firstname', max_length=100, blank=True, null=True)  # Field name made lowercase.
    lastname = models.CharField(db_column='Lastname', max_length=100, blank=True, null=True)  # Field name made lowercase.
    middlename = models.CharField(db_column='Middlename', max_length=100, blank=True, null=True)  # Field name made lowercase.
    contactno = models.CharField(db_column='ContactNo', unique=True, max_length=20, blank=True, null=True)  # Field name made lowercase.
    sex = models.CharField(db_column='Sex', max_length=10, blank=True, null=True)  # Field name made lowercase.
    is_verified = models.IntegerField()
    is_active = models.IntegerField()
    is_first_login = models.IntegerField()
    is_password_changed = models.IntegerField()
    created_at = models.DateTimeField()
    position = models.ForeignKey(Positions, models.DO_NOTHING, blank=True, null=True)
    role = models.ForeignKey(Roles, models.DO_NOTHING, blank=True, null=True)
    user_type = models.ForeignKey(Usertypes, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'Users'


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.IntegerField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.IntegerField()
    is_active = models.IntegerField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.PositiveSmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'
