def is_assinante(user):
    return (
        user.is_authenticated
        and not user.is_superuser
        and user.groups.filter(name='assinante').exists()
    )
